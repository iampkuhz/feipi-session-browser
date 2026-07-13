#!/usr/bin/env python3
"""解析共享 Python interpreter，并检查依赖契约。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
import shutil
import subprocess
import sys

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
_TEST_PACKAGES = {'pytest', 'pytest-xdist'}
_NORMALIZE_RE = re.compile(r'[-_.]+')


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


# 判断解释器版本是否满足项目 Python 约束。
def _supports_python_version(executable: str) -> bool:
    """参数：
        executable: 待探测的 Python executable。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    if not _is_executable(executable):
        return False
    code = 'import sys; raise SystemExit(0 if (3, 12) <= sys.version_info[:2] < (3, 13) else 1)'
    try:
        result = subprocess.run(
            [executable, '-c', code],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return result.returncode == 0


# 维护Python 候选项。
def python_candidates(repo_root: Path = REPO_ROOT) -> list[str]:
    """参数：
        repo_root: 仓库根目录。

    返回：
        结果列表。
    """
    candidates: list[str] = []
    explicit = os.environ.get('SESSION_BROWSER_PYTHON')
    if explicit:
        candidates.append(explicit)

    venv_dir = os.environ.get('SESSION_BROWSER_VENV_DIR')
    if venv_dir:
        candidates.append(str(Path(venv_dir).expanduser() / 'bin' / 'python'))
    else:
        candidates.append(str(repo_root / '.venv' / 'bin' / 'python'))

    candidates.extend(['python', 'python3'])

    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


# 解析Python。
def resolve_python(repo_root: Path = REPO_ROOT) -> str:
    """参数：
        repo_root: 仓库根目录。

    返回：
        resolve python 字符串。
    """
    explicit = os.environ.get('SESSION_BROWSER_PYTHON')
    for candidate in python_candidates(repo_root):
        if _supports_python_version(candidate):
            return candidate
        if explicit and candidate == explicit:
            raise SystemExit(
                f'SESSION_BROWSER_PYTHON 不可执行或不满足 Python {PYTHON_REQUIRES}: {explicit}'
            )
    raise SystemExit(f'未找到可用 Python 解释器(需要 Python {PYTHON_REQUIRES})。')


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


if __name__ == '__main__':
    raise SystemExit(main())
