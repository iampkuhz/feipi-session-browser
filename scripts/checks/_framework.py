"""负责共享 check 结果、诊断与领域函数调用协议；不负责选择 Gate；由检查命令行入口调用。"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import inspect
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

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
    """保存一次 check 的统一状态与诊断。"""

    check_id: str
    passed: bool
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """绑定公开 check ID 与领域函数。"""

    check_id: str
    module: str
    function: str = 'main'

    def load(self) -> Callable[..., object]:
        """延迟加载领域函数，避免无关 check 的 import side effect。"""
        return getattr(importlib.import_module(self.module), self.function)


def invoke(spec: CheckSpec, arguments: list[str]) -> CheckResult:
    """调用领域函数并把退出码、输出或异常归一为 CheckResult。"""
    function = spec.load()
    stdout, stderr = io.StringIO(), io.StringIO()
    original_argv = sys.argv
    try:
        sys.argv = [spec.module, *arguments]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            parameters = inspect.signature(function).parameters
            value = function(arguments) if parameters else function()
    except SystemExit as exc:
        value = exc.code
    except Exception as exc:  # noqa: BLE001 - CLI 边界必须归一化领域异常。
        return CheckResult(spec.check_id, False, (Diagnostic(f'{type(exc).__name__}: {exc}'),))
    finally:
        sys.argv = original_argv
    if isinstance(value, CheckResult):
        return value
    if isinstance(value, (list, tuple)):
        diagnostics = tuple(Diagnostic(str(item)) for item in value)
        return CheckResult(spec.check_id, not diagnostics, diagnostics)
    passed = (
        value is None
        or value is True
        or (isinstance(value, int) and not isinstance(value, bool) and value == 0)
    )
    if passed:
        return CheckResult(spec.check_id, True)
    lines = [
        line for line in (*stdout.getvalue().splitlines(), *stderr.getvalue().splitlines()) if line
    ]
    diagnostics = tuple(Diagnostic(line) for line in lines) or (Diagnostic(f'exit code: {value}'),)
    return CheckResult(spec.check_id, False, diagnostics)
