"""检查并定义所有领域 Check 共同遵守的调用协议，用于保证一致的执行边界。

每个领域模块的唯一公开入口是 ``check(arguments) -> CheckResult``。本模块负责加载入口并捕获
异常，不负责判断具体业务规则；失败表示协议无法加载或领域检查返回违规诊断。"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


class CheckStatus(StrEnum):
    """定义 Python Check 对 Execution adapter 输出的三态结论。"""

    PASS = 'PASS'
    BLOCKED = 'BLOCKED'
    FAIL = 'FAIL'


def repository_root() -> Path:
    """返回当前 checkout 的 repository root。"""
    return Path(__file__).resolve().parents[3]


def argument_parser(description: str = '') -> argparse.ArgumentParser:
    """创建领域参数声明使用的共享 parser。"""
    return argparse.ArgumentParser(description=description)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """保存一条稳定、可定位的 check 诊断。"""

    message: str
    path: str = ''
    line: int = 0

    def render(self) -> str:
        """返回共享 CLI 的稳定单行格式。"""
        location = f'{self.path}:{self.line}: ' if self.path else ''
        return f'{location}{self.message}'


@dataclass(frozen=True, slots=True)
class CheckResult:
    """保存 Check 结论；规则命中为 BLOCKED，执行异常为 FAIL。"""

    diagnostics: tuple[Diagnostic, ...] = ()
    outcome: CheckStatus = CheckStatus.BLOCKED
    reason: str = ''

    @property
    def passed(self) -> bool:
        """仅当没有任何失败诊断时返回 True。"""
        return not self.diagnostics

    @property
    def status(self) -> CheckStatus:
        """返回结构化状态；没有诊断时固定为 PASS。"""
        return CheckStatus.PASS if self.passed else self.outcome

    @classmethod
    def from_errors(cls, errors: Iterable[object]) -> CheckResult:
        """把完整执行后发现的领域违规转换为 BLOCKED。"""
        return cls(
            tuple(
                item if isinstance(item, Diagnostic) else Diagnostic(str(item)) for item in errors
            )
        )

    @classmethod
    def execution_failure(
        cls, errors: Iterable[object], *, reason: str = 'outcome-unknown'
    ) -> CheckResult:
        """把 runtime、输入或依赖异常转换为没有检查结论的 FAIL。"""
        diagnostics = tuple(
            item if isinstance(item, Diagnostic) else Diagnostic(str(item)) for item in errors
        )
        return cls(diagnostics, CheckStatus.FAIL, reason)


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """绑定公开 check ID 与唯一领域模块。"""

    check_id: str
    module: str


def invoke(spec: CheckSpec, arguments: list[str]) -> CheckResult:
    """调用唯一 `check` 入口，并把参数错误或异常转换为失败诊断。"""
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            function = vars(importlib.import_module(spec.module)).get('check')
            if not callable(function):
                raise TypeError(f'{spec.module}.check is not callable')
            result = function(arguments)
    except SystemExit as exc:
        # argparse 使用 SystemExit(0) 表示正常展示帮助；它不是领域规则失败。
        if exc.code is None or (
            isinstance(exc.code, int) and not isinstance(exc.code, bool) and exc.code == 0
        ):
            return CheckResult()
        lines = [
            line
            for line in (*stdout.getvalue().splitlines(), *stderr.getvalue().splitlines())
            if line
        ]
        return CheckResult.execution_failure(
            lines or [f'argument parser exit code: {exc.code}'], reason='input-unavailable'
        )
    except Exception as exc:  # noqa: BLE001 - CLI 边界必须归一化领域异常。
        return CheckResult.execution_failure(
            [f'{type(exc).__name__}: {exc}'], reason='outcome-unknown'
        )
    if not isinstance(result, CheckResult):
        return CheckResult.execution_failure(
            [f'{spec.module}.check must return CheckResult, got {type(result).__name__}'],
            reason='outcome-unknown',
        )
    return result
