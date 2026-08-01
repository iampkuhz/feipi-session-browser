#!/usr/bin/env python3
"""解析共享 Python interpreter，并检查依赖契约。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None  # type: ignore[assignment]
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_VERSION = (3, 12)
MAX_VERSION = (3, 13)
PYTHON_REQUIRES = '>=3.12,<3.13'
UV_PYTHON_REQUIRES = '==3.12.*'
_PYTHON_VERSION_LOCK = '.python-version'
_UV_LOCK = 'uv.lock'
DEFAULT_VENV_RELATIVE_PATH = Path('.local/python/venv')
DEV_SYNC_COMMAND = 'UV_PROJECT_ENVIRONMENT=.local/python/venv uv sync --frozen --extra dev'
_TEST_PACKAGES = {'pytest', 'pytest-xdist'}
_NORMALIZE_RE = re.compile(r'[-_.]+')
_IMPORT_NAME_OVERRIDES = {'pyyaml': 'yaml'}
_PROBE_TIMEOUT_SECONDS = 0.45
_RESOLVE_BUDGET_SECONDS = 1.5


@dataclass(frozen=True, slots=True)
class PythonCandidateCheck:
    """仅保留候选来源与状态，诊断输出不得回显环境中的解释器路径。"""

    source: str
    status: str


class ProjectPythonNotReadyError(RuntimeError):
    """表示没有同时满足版本与 runtime dependency contract 的解释器。"""

    code = 'BLOCKED_PROJECT_PYTHON_NOT_READY'

    def __init__(self, repo_root: Path, checks: list[PythonCandidateCheck]):
        super().__init__(self.code)
        self.repo_root = Path(repo_root).resolve()
        self.checks = tuple(checks)

    def render(self) -> str:
        """生成不泄露解释器路径的项目 Python 就绪诊断。"""

        checked = [{'source': item.source, 'status': item.status} for item in self.checks]
        return '\n'.join(
            (
                self.code,
                f'repoRoot: {self.repo_root}',
                f'checkedCandidates: {json.dumps(checked, separators=(",", ":"))}',
                f'remediation: {DEV_SYNC_COMMAND}',
            )
        )


def normalize_name(name: str) -> str:
    """按 Python distribution 规范统一依赖名，供 metadata 与 lock 比对。"""
    return _NORMALIZE_RE.sub('-', name).lower()


def _is_executable(path: str) -> bool:
    """判断命令名或文件路径是否指向可执行文件。"""
    if os.sep in path or (os.altsep and os.altsep in path):
        return Path(path).expanduser().is_file() and os.access(Path(path).expanduser(), os.X_OK)
    return shutil.which(path) is not None


def project_venv_dir(repo_root: Path = REPO_ROOT) -> Path:
    """返回显式配置或仓库默认 Python venv 的绝对路径。"""

    configured = os.environ.get('SESSION_BROWSER_VENV_DIR', '').strip()
    candidate = (
        Path(configured).expanduser() if configured else repo_root / DEFAULT_VENV_RELATIVE_PATH
    )
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def _candidate_specs(repo_root: Path) -> list[tuple[str, str]]:
    """按显式配置、项目 venv、系统解释器的优先级生成去重候选。"""

    explicit = os.environ.get('SESSION_BROWSER_PYTHON', '').strip()
    if explicit:
        return [('explicit', explicit)]
    candidates: list[tuple[str, str]] = [
        ('project-venv', str(project_venv_dir(repo_root) / 'bin' / 'python'))
    ]
    candidates.extend((('system-python', 'python'), ('system-python3', 'python3')))
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source, candidate in candidates:
        resolved = shutil.which(candidate) if os.sep not in candidate else candidate
        key = str(Path(resolved or candidate).expanduser().resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append((source, candidate))
    return result


def _runtime_import_names(repo_root: Path) -> tuple[str, ...]:
    """从 pyproject 读取 runtime dependency，并映射为最小 import 名。"""

    path = repo_root / 'pyproject.toml'
    if not path.is_file():
        return ()
    if tomllib is None:
        dependencies, _dev = _parse_pyproject_arrays(path)
    else:
        project = tomllib.loads(path.read_text(encoding='utf-8')).get('project', {})
        dependencies = [str(item) for item in project.get('dependencies', [])]
    names = []
    for dependency in dependencies:
        match = re.match(r'[A-Za-z0-9_.-]+', dependency.strip())
        if not match:
            continue
        distribution = normalize_name(match.group(0))
        names.append(_IMPORT_NAME_OVERRIDES.get(distribution, distribution.replace('-', '_')))
    return tuple(sorted(set(names)))


def _probe_python(
    executable: str,
    repo_root: Path,
    *,
    timeout_seconds: float,
) -> str:
    """用单个短进程同时验证 Python 版本与 runtime import。"""

    if not _is_executable(executable):
        return 'missing'
    imports = _runtime_import_names(repo_root)
    code = (
        'import importlib,sys;'
        'ok=(3,12)<=sys.version_info[:2]<(3,13);'
        f'mods={imports!r};'
        'raise SystemExit(3 if not ok else 0 if all(importlib.import_module(m) for m in mods) else 4)'
    )
    try:
        result = subprocess.run(
            [executable, '-c', code],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(0.05, timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 'timeout'
    except OSError:
        return 'missing'
    if result.returncode == 0:
        return 'ready'
    if result.returncode == 3:
        return 'wrong-version'
    return 'dependency-not-ready'


def python_candidates(repo_root: Path = REPO_ROOT) -> list[str]:
    """返回 resolver 会依次探测的 Python executable。"""
    return [candidate for _source, candidate in _candidate_specs(repo_root)]


def resolve_python(repo_root: Path = REPO_ROOT) -> str:
    """在总时间预算内选择首个满足版本和 runtime dependency 契约的解释器。

    显式配置失败时不会降级到其他候选，避免用户指定的环境被静默绕过。
    """
    started = time.monotonic()
    checks: list[PythonCandidateCheck] = []
    for source, candidate in _candidate_specs(repo_root):
        remaining = _RESOLVE_BUDGET_SECONDS - (time.monotonic() - started)
        if remaining <= 0:
            checks.append(PythonCandidateCheck(source, 'timeout'))
            break
        status = _probe_python(
            candidate,
            repo_root,
            timeout_seconds=min(_PROBE_TIMEOUT_SECONDS, remaining),
        )
        checks.append(PythonCandidateCheck(source, status))
        if status == 'ready':
            return candidate
        if source == 'explicit':
            break
    raise ProjectPythonNotReadyError(repo_root, checks)


def _parse_version(value: str) -> tuple[int, int, int] | None:
    """把三段 Python 版本解析为可比较 tuple，格式不合法时返回 None。"""
    parts = value.strip().split('.')
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def _version_in_range(version: tuple[int, int, int]) -> bool:
    """判断版本是否满足项目固定的 Python minor 契约。"""
    major_minor = version[:2]
    return MIN_VERSION <= major_minor < MAX_VERSION


def _pyproject_requires_python(path: Path) -> str:
    """读取 pyproject.toml 的 requires-python，缺失时返回空字符串。"""
    if tomllib is None:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line.startswith('requires-python'):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
        return ''
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    return str(data.get('project', {}).get('requires-python', ''))


def _uv_requires_python(path: Path) -> str:
    """读取 uv.lock 的 requires-python，文件或字段缺失时返回空字符串。"""
    if not path.is_file():
        return ''
    for raw in path.read_text(encoding='utf-8').splitlines()[:20]:
        line = raw.strip()
        if line.startswith('requires-python'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def _python_contract_problems(repo_root: Path) -> list[str]:
    """汇总 pyproject、uv.lock 与 .python-version 之间的版本口径漂移。"""
    problems: list[str] = []
    pyproject_requires = _pyproject_requires_python(repo_root / 'pyproject.toml')
    if pyproject_requires != PYTHON_REQUIRES:
        problems.append(f'pyproject requires-python 应为 {PYTHON_REQUIRES}: {pyproject_requires}')
    uv_requires = _uv_requires_python(repo_root / 'uv.lock')
    if uv_requires and uv_requires not in {PYTHON_REQUIRES, UV_PYTHON_REQUIRES}:
        problems.append(
            f'uv.lock requires-python 应为 {PYTHON_REQUIRES} '
            f'或等价的 {UV_PYTHON_REQUIRES}: {uv_requires}'
        )
    lock_path = repo_root / _PYTHON_VERSION_LOCK
    if not lock_path.is_file():
        problems.append(f'缺少 Python 版本契约: {_PYTHON_VERSION_LOCK}')
        return problems
    raw_version = lock_path.read_text(encoding='utf-8').strip()
    version = _parse_version(raw_version)
    if version is None or not _version_in_range(version):
        problems.append(f'{_PYTHON_VERSION_LOCK} 必须锁定到 Python 3.12 patch: {raw_version}')
    return problems


def _parse_pyproject_arrays(path: Path) -> tuple[list[str], list[str]]:
    """在 tomllib 不可用时解析项目维护的简单 dependency 数组结构。"""
    text = path.read_text(encoding='utf-8')
    deps: list[str] = []
    dev: list[str] = []
    current: str | None = None
    in_array = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == 'dependencies = [':
            current = 'dependencies'
            in_array = True
            continue
        if line == 'dev = [':
            current = 'dev'
            in_array = True
            continue
        if in_array and line == ']':
            current = None
            in_array = False
            continue
        if in_array and current in {'dependencies', 'dev'}:
            item = line.rstrip(',').strip().strip('"').strip("'")
            if item:
                (deps if current == 'dependencies' else dev).append(normalize_name(item))
    return deps, dev


def pyproject_names(path: Path) -> tuple[list[str], list[str]]:
    """返回 pyproject 声明的 runtime 与 dev distribution 名。"""
    if tomllib is None:
        return _parse_pyproject_arrays(path)
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    project = data.get('project', {})
    deps = [normalize_name(item) for item in project.get('dependencies', [])]
    dev = [normalize_name(item) for item in project.get('optional-dependencies', {}).get('dev', [])]
    return deps, dev


def check_locks(repo_root: Path = REPO_ROOT) -> list[str]:
    """检查 Python 版本文件与唯一 uv lock 是否齐全、口径一致。"""
    problems: list[str] = []
    problems.extend(_python_contract_problems(repo_root))
    if not (repo_root / _UV_LOCK).is_file():
        problems.append(f'缺少锁文件: {_UV_LOCK}')
    return problems


def installed_problems(profile: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """汇总指定依赖 profile 中尚未安装的 distribution。"""
    runtime, dev = pyproject_names(repo_root / 'pyproject.toml')
    if profile == 'runtime':
        names = set(runtime)
    elif profile == 'test':
        names = set(runtime) | _TEST_PACKAGES
    elif profile == 'dev':
        names = set(runtime) | set(dev)
    else:
        raise ValueError(f'unknown profile: {profile}')

    problems: list[str] = []
    for name in sorted(names):
        try:
            importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f'缺少 Python 依赖: {name}')
    return problems


def print_report(repo_root: Path = REPO_ROOT) -> int:
    """打印 Python 依赖契约摘要，并以退出码表示 lock 是否一致。"""
    python = resolve_python(repo_root)
    print(f'[INFO] python: {python}')
    print(f'[INFO] python requires: {PYTHON_REQUIRES}')
    print(f'[INFO] python lock: {_PYTHON_VERSION_LOCK}')
    print(f'[INFO] python candidates: {", ".join(python_candidates(repo_root))}')
    print('[INFO] dependencies: pyproject.toml')
    print(f'[INFO] lock: {_UV_LOCK}')
    problems = check_locks(repo_root)
    if problems:
        for problem in problems:
            print(f'[FAIL] {problem}', file=sys.stderr)
        return 1
    print('[PASS] Python dependency truth is pyproject.toml + uv.lock')
    return 0


def main(argv: list[str] | None = None) -> int:
    """解析子命令并运行 resolver、报告或依赖契约检查。"""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('resolve')
    sub.add_parser('report')
    sub.add_parser('check-locks')
    installed = sub.add_parser('check-installed')
    installed.add_argument('--profile', choices=['runtime', 'test', 'dev'], default='runtime')
    args = parser.parse_args(argv)

    try:
        if args.cmd == 'resolve':
            print(resolve_python())
            return 0
        if args.cmd == 'report':
            return print_report()
        problems = check_locks() if args.cmd == 'check-locks' else installed_problems(args.profile)
        if problems:
            for problem in problems:
                print(f'[FAIL] {problem}', file=sys.stderr)
            return 1
        print(
            '[PASS] '
            + (
                'Python dependency contract present'
                if args.cmd == 'check-locks'
                else f'{args.profile} dependencies installed'
            )
        )
        return 0
    except ProjectPythonNotReadyError as exc:
        print(exc.render(), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
