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
                'remediation: ./scripts/session-browser.sh deps --dev',
            )
        )


# 规范化name。
def normalize_name(name: str) -> str:
    """参数：
        name: 原始dependency name从project metadata 或 lock 文件。

    返回：
        normalize name 字符串。
    """
    return _NORMALIZE_RE.sub('-', name).lower()


# 判断是否executable。
def _is_executable(path: str) -> bool:
    """参数：
        path: 命令name 或 filesystem 路径以检查。

    返回：
        满足条件时返回 true，否则返回 false。
    """
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


# 判断解释器版本是否满足项目 Python 约束。
def _candidate_specs(repo_root: Path) -> list[tuple[str, str]]:
    """按显式、项目 venv、系统解释器生成去重候选。"""

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


# 维护Python 候选项。
def python_candidates(repo_root: Path = REPO_ROOT) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    return [candidate for _source, candidate in _candidate_specs(repo_root)]


# 解析Python。
def resolve_python(repo_root: Path = REPO_ROOT) -> str:
    """参数：
        repo_root: 仓库根目录。

    返回：
        resolve python 字符串。
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


# 解析版本tuple。
def _parse_version(value: str) -> tuple[int, int, int] | None:
    """参数：
        value: 版本字符串，例如 ``3.12.11``。

    返回：
        可比较的三段版本；无法解析时返回 None。
    """
    parts = value.strip().split('.')
    if len(parts) != 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


# 判断版本是否满足项目 Python minor 合约。
def _version_in_range(version: tuple[int, int, int]) -> bool:
    """参数：
        version: 三段 Python 版本。

    返回：
        满足 ``>=3.12,<3.13`` 时返回 true。
    """
    major_minor = version[:2]
    return MIN_VERSION <= major_minor < MAX_VERSION


# 读取 pyproject 中声明的 Python 版本约束。
def _pyproject_requires_python(path: Path) -> str:
    """参数：
        path: pyproject.toml 路径。

    返回：
        requires-python 字符串，缺失时为空。
    """
    if tomllib is None:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if line.startswith('requires-python'):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
        return ''
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    return str(data.get('project', {}).get('requires-python', ''))


# 读取 uv.lock requires-python。
def _uv_requires_python(path: Path) -> str:
    """参数：
        path: uv.lock 路径。

    返回：
        lock 文件声明的 requires-python。
    """
    if not path.is_file():
        return ''
    for raw in path.read_text(encoding='utf-8').splitlines()[:20]:
        line = raw.strip()
        if line.startswith('requires-python'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


# 检查 Python 版本合约文件。
def _python_contract_problems(repo_root: Path) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        Python 版本合约 drift 列表。
    """
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


# 解析 pyproject 中的数组字段。
def _parse_pyproject_arrays(path: Path) -> tuple[list[str], list[str]]:
    """参数：
        path: 待检查的路径。

    返回：
        结果 tuple。
    """
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


# 维护pyproject names。
def pyproject_names(path: Path) -> tuple[list[str], list[str]]:
    """参数：
        path: Pyproject 文件到解析。

    返回：
        结果 tuple。
    """
    if tomllib is None:
        return _parse_pyproject_arrays(path)
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    project = data.get('project', {})
    deps = [normalize_name(item) for item in project.get('dependencies', [])]
    dev = [normalize_name(item) for item in project.get('optional-dependencies', {}).get('dev', [])]
    return deps, dev


# 检查locks。
def check_locks(repo_root: Path = REPO_ROOT) -> list[str]:
    """检查 Python 版本文件与唯一 uv lock 是否齐全、口径一致。"""
    problems: list[str] = []
    problems.extend(_python_contract_problems(repo_root))
    if not (repo_root / _UV_LOCK).is_file():
        problems.append(f'缺少锁文件: {_UV_LOCK}')
    return problems


# 汇总已安装依赖与契约不一致的问题。
def installed_problems(profile: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """参数：
        profile: profile 参数。
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
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


# 打印报告。
def print_report(repo_root: Path = REPO_ROOT) -> int:
    """参数：
        repo_root: 仓库根目录。

    返回：
        进程退出码。
    """
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


# 解析命令行参数并运行脚本入口。
def main(argv: list[str] | None = None) -> int:
    """参数：
        argv: 可选命令-行 参数; defaults到``sys.argv``。

    返回：
        进程退出码。
    """
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
