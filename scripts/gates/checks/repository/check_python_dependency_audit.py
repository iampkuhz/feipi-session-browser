"""执行 Python 锁定依赖漏洞检查。

为确保提交使用的完整锁定依赖没有已知漏洞，唯一入口 ``check(arguments)`` 串行执行 frozen
lock export 和 pip-audit。Check 自己返回结构化失败诊断：真实漏洞为 ``BLOCKED``，工具、依赖或网络导致
审计未完成时为 ``FAIL``；Executor 不再猜测自然语言日志。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.gates.checks.check_protocol import CheckResult, argument_parser, repository_root

ROOT = repository_root()
_NETWORK_ENV_KEYS = (
    'HTTPS_PROXY',
    'HTTP_PROXY',
    'ALL_PROXY',
    'https_proxy',
    'http_proxy',
    'all_proxy',
)
_NETWORK_MARKERS = (
    'requests.exceptions.SSLError',
    'requests.exceptions.ProxyError',
    'requests.exceptions.ReadTimeout',
    'urllib3.exceptions.ReadTimeoutError',
    'urllib3.exceptions.MaxRetryError',
    'HTTPSConnectionPool',
    'RemoteDisconnected',
    'UNEXPECTED_EOF_WHILE_READING',
)
_MAX_DIAGNOSTIC_LINES = 40
_MAX_DIAGNOSTIC_CHARS = 4000


def _environment() -> dict[str, str]:
    """返回审计子进程环境；默认不继承可能改变结果的本机代理。"""
    environment = os.environ.copy()
    if environment.get('SESSION_BROWSER_AUDIT_USE_PROXY') != '1':
        for key in _NETWORK_ENV_KEYS:
            environment.pop(key, None)
    return environment


def _run(
    command: list[str], *, root: Path, input_text: str | None = None
) -> subprocess.CompletedProcess:
    """执行一个安全工具并完整捕获文本输出。"""
    return subprocess.run(
        command,
        cwd=root,
        env=_environment(),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _redact(line: str) -> str:
    """遮盖常见凭据形式，避免底层工具错误把本机认证信息带入诊断。"""
    line = re.sub(r'(?i)(authorization:\s*(?:bearer\s+)?)[^\s]+', r'\1<redacted>', line)
    line = re.sub(r'(?i)((?:token|api[_-]?key|secret|password)=)[^&\s]+', r'\1<redacted>', line)
    return re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@', r'\1<redacted>@', line)


def _output(process: subprocess.CompletedProcess) -> str:
    """返回有界、脱敏输出，并确保网络归约所需标记不会因截断丢失。"""
    raw = '\n'.join(part.strip() for part in (process.stdout, process.stderr) if part.strip())
    lines = [_redact(line) for line in raw.splitlines()]
    if len(lines) > _MAX_DIAGNOSTIC_LINES:
        edge_count = (_MAX_DIAGNOSTIC_LINES - 2) // 2
        selected = [*lines[:edge_count], '[diagnostic truncated]', *lines[-edge_count:]]
    else:
        selected = lines
    network_line = next(
        (line for line in lines if any(item in line for item in _NETWORK_MARKERS)), ''
    )
    if network_line and network_line not in selected:
        selected.append(network_line)
    rendered = '\n'.join(selected)
    if len(rendered) <= _MAX_DIAGNOSTIC_CHARS:
        return rendered
    suffix_line = network_line[:500] if network_line else '[diagnostic truncated]'
    suffix = f'\n[diagnostic truncated]\n{suffix_line}'
    return f'{rendered[: _MAX_DIAGNOSTIC_CHARS - len(suffix)]}{suffix}'


def _failure(tool: str, process: subprocess.CompletedProcess) -> CheckResult:
    """区分漏洞结论与审计工具自身未完成，避免 executor 猜测日志。"""
    detail = _output(process) or f'exit code {process.returncode}'
    message = f'[python-dependency-audit] {tool}:\n{detail}'
    if any(marker in detail for marker in _NETWORK_MARKERS):
        return CheckResult.execution_failure([message], reason='network-unavailable')
    if tool == 'pip-audit':
        # pip-audit 正常完成且以 1 报出漏洞，属于明确的仓库阻断结论。
        if process.returncode == 1:
            return CheckResult.from_errors([message])
        return CheckResult.execution_failure([message], reason='outcome-unknown')
    return CheckResult.execution_failure([message], reason='dependency-unavailable')


def check(arguments: list[str]) -> CheckResult:
    """解析仓库路径，依次导出并审计锁定依赖。"""
    parser = argument_parser(description='Check locked Python dependencies for vulnerabilities.')
    parser.add_argument('--root', default=str(ROOT), help='Repository root to inspect')
    args = parser.parse_args(arguments)
    root = Path(args.root).resolve()

    uv = shutil.which('uv')
    if uv is None:
        return CheckResult.execution_failure(
            ['[python-dependency-audit] uv: command not found'],
            reason='runtime-missing',
        )

    exported = _run(
        [
            uv,
            'export',
            '--frozen',
            '--extra',
            'dev',
            '--no-hashes',
            '--no-emit-project',
            '--no-header',
            '--no-annotate',
        ],
        root=root,
    )
    if exported.returncode != 0:
        return _failure('uv export', exported)

    audited = _run(
        [
            sys.executable,
            '-m',
            'pip_audit',
            '-s',
            'osv',
            '-r',
            '/dev/stdin',
            '--no-deps',
            '--disable-pip',
            '--progress-spinner',
            'off',
            '--timeout',
            '60',
        ],
        root=root,
        input_text=exported.stdout,
    )
    if audited.returncode != 0:
        return _failure('pip-audit', audited)
    return CheckResult()
