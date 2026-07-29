"""定义所有领域 Check 共同遵守的调用协议。

每个 `check_*.py` 文件只公开 `check(arguments) -> CheckResult`。本模块负责加载该入口、捕获异常并
把诊断交给统一命令行输出；本模块不负责判断具体业务规则。
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

CheckOptions = argparse.Namespace


def repository_root() -> Path:
    """返回当前 checkout 的 repository root。"""
    return Path(__file__).resolve().parents[2]


def argument_parser(description: str = '') -> argparse.ArgumentParser:
    """创建领域参数声明使用的共享 parser。"""
    return argparse.ArgumentParser(description=description)


def parse_changed_files(raw: str | None) -> list[str] | None:
    """兼容领域参数时只做 JSON 解码；Gate applicability 仍仅由 planner 决定。"""
    return json.loads(raw) if raw and raw.strip() else None


def add_changed_files_arg(parser: argparse.ArgumentParser) -> None:
    """为仍消费精确输入的领域算法声明数据参数，不进行 trigger 判断。"""
    parser.add_argument('--changed-files')


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
    """保存一个 Check 返回的全部失败诊断；没有诊断即表示通过。"""

    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def passed(self) -> bool:
        """仅当没有任何失败诊断时返回 True。"""
        return not self.diagnostics

    @classmethod
    def from_errors(cls, errors: Iterable[object]) -> CheckResult:
        """把领域规则产生的错误转换成统一诊断。"""
        return cls(
            tuple(
                item if isinstance(item, Diagnostic) else Diagnostic(str(item)) for item in errors
            )
        )


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """绑定公开 check ID 与唯一领域模块。"""

    check_id: str
    module: str

    def load(self) -> Callable[[list[str]], CheckResult]:
        """延迟加载模块中固定命名的 `check` 入口。"""
        function = vars(importlib.import_module(self.module)).get('check')
        if not callable(function):
            raise TypeError(f'{self.module}.check is not callable')
        return function


def invoke(spec: CheckSpec, arguments: list[str]) -> CheckResult:
    """调用唯一 `check` 入口，并把参数错误或异常转换为失败诊断。"""
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = spec.load()(arguments)
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
        return CheckResult.from_errors(lines or [f'argument parser exit code: {exc.code}'])
    except Exception as exc:  # noqa: BLE001 - CLI 边界必须归一化领域异常。
        return CheckResult.from_errors([f'{type(exc).__name__}: {exc}'])
    if not isinstance(result, CheckResult):
        return CheckResult.from_errors(
            [f'{spec.module}.check must return CheckResult, got {type(result).__name__}']
        )
    return result
