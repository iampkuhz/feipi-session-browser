"""统一检查测试数据是否可复现且不依赖个人电脑环境。

唯一入口 ``check(arguments)`` 检查两件事：仓库内 fixture/resource 必须被 Git 跟踪；测试源码
与这些数据不得包含真实 Session、个人用户名或固定个人设备路径。诊断只报告相对路径、行号和
规则名，不复述命中的敏感内容。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from collections.abc import Iterable

ROOT = repository_root()

_TEXT_SUFFIXES = {
    '.css',
    '.csv',
    '.html',
    '.java',
    '.js',
    '.json',
    '.jsonl',
    '.kt',
    '.md',
    '.properties',
    '.py',
    '.sh',
    '.sql',
    '.ts',
    '.txt',
    '.xml',
    '.yaml',
    '.yml',
}
_IGNORED_PARTS = {'__pycache__', 'build', '.gradle', 'node_modules', '.local', 'venv'}
_SYNTHETIC_USERS = {
    'admin',
    'alice',
    'bob',
    'demo',
    'dev',
    'developer',
    'example',
    'test',
    'testuser',
    'user',
    'username',
    'your-username',
}
_PERSONAL_USER = ''.join(('zhe', 'han'))
_HOME_RE = re.compile(r'(?P<prefix>/Users/|/home/)(?P<user>[^/"\'\s\\]+)')
_WINDOWS_HOME_RE = re.compile(r'(?i)[A-Z]:\\Users\\(?P<user>[^\\"\'\s]+)')
_REAL_SESSION_RE = re.compile(
    r'(?:/Users/|/home/)[^/\s]+/(?:\.claude/projects|\.codex/sessions|\.qoder/sessions)/'
)
_RAW_SESSION_MARKERS = ('"parentUuid"', '"promptId"', '"messageId"', '"toolUseResult"')
_ABSOLUTE_DATA_SOURCE_RE = re.compile(r'''\b(?:open|Path)\s*\(\s*[rR]?["'](?:/(?!/)|[A-Za-z]:\\)''')


def _is_managed_data(path: Path, root: Path) -> bool:
    """判断普通文件是否位于统一管理的测试数据目录。"""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    is_fixture = len(parts) >= 3 and parts[0] == 'tests' and 'fixtures' in parts[1:-1]
    is_java_resource = parts[0] == 'java' and any(
        tuple(parts[index : index + 3]) == ('src', 'test', 'resources')
        for index in range(len(parts) - 2)
    )
    return is_fixture or is_java_resource


def _iter_managed_data(root: Path) -> list[Path]:
    """枚举所有 fixture 和 Java test resource 普通文件。"""
    roots = [root / 'tests', root / 'java']
    return sorted(
        path
        for scan_root in roots
        if scan_root.is_dir()
        for path in scan_root.rglob('*')
        if path.is_file()
        and not path.is_symlink()
        and not set(path.relative_to(root).parts).intersection(_IGNORED_PARTS)
        and _is_managed_data(path, root)
    )


def _iter_test_sources(root: Path) -> list[Path]:
    """枚举 Python/Playwright 及 Java 测试源码，不扫描构建产物。"""
    candidates: list[Path] = []
    tests_root = root / 'tests'
    if tests_root.is_dir():
        candidates.extend(tests_root.rglob('*'))
    java_root = root / 'java'
    if java_root.is_dir():
        candidates.extend(java_root.glob('**/src/test/**/*'))
    return sorted(
        path
        for path in candidates
        if path.is_file()
        and path.suffix.lower() in _TEXT_SUFFIXES
        and not set(path.relative_to(root).parts).intersection(_IGNORED_PARTS)
    )


def _git_tracked_files(root: Path) -> tuple[set[str], str | None]:
    """读取 Git 跟踪清单；任何调用或解码失败都返回关闭式错误。"""
    try:
        result = subprocess.run(
            ['git', '-C', str(root), 'ls-files', '-z', '--', 'tests', 'java'],
            capture_output=True,
            check=False,
        )
    except OSError:
        return set(), 'git-tracked-files-unavailable'
    if result.returncode != 0:
        return set(), 'git-tracked-files-unavailable'
    try:
        output = result.stdout.decode('utf-8')
    except UnicodeDecodeError:
        return set(), 'git-tracked-files-unavailable'
    return {item for item in output.split('\0') if item}, None


def _is_explicit_synthetic_record(line: str) -> bool:
    """仅把明确声明 synthetic=true 的 JSON 记录视为合成 Session。"""
    try:
        value = json.loads(line)
    except (TypeError, ValueError):
        return False
    return isinstance(value, dict) and value.get('synthetic') is True


def _line_rules(line: str, *, source_file: bool) -> set[str]:
    """返回一行命中的规则名；不返回原始文本以避免诊断泄露。"""
    rules: set[str] = set()
    stripped = line.lstrip()
    if source_file and stripped.startswith(('#', '//', '/*', '*')):
        return rules
    if _PERSONAL_USER in line.lower():
        rules.add('known-personal-username')
    if _REAL_SESSION_RE.search(line):
        rules.add('real-session-path')

    homes = [match.group('user') for match in _HOME_RE.finditer(line)]
    homes.extend(match.group('user') for match in _WINDOWS_HOME_RE.finditer(line))
    if any(user.lower() not in _SYNTHETIC_USERS for user in homes):
        rules.add('personal-device-path')
    # 测试数据必须来自仓库或框架临时目录；硬编码绝对路径作为读取入口一律拒绝。
    # tmp_path、@TempDir、tempfile 等动态构造不包含绝对路径字面量，因此不会误伤。
    if source_file and _ABSOLUTE_DATA_SOURCE_RE.search(line):
        rules.add('external-test-data-source')

    marker_count = sum(marker in line for marker in _RAW_SESSION_MARKERS)
    if marker_count >= 2 and not _is_explicit_synthetic_record(line.strip()):
        rules.add('raw-session-content')
    return rules


def _scan_text_files(root: Path, files: Iterable[Path]) -> list[str]:
    """扫描测试源码和受管数据；无法读取的文本文件按关闭式策略失败。"""
    errors: list[str] = []
    managed = set(_iter_managed_data(root))
    for path in sorted(set(files)):
        relative = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeDecodeError):
            errors.append(f'{relative}: unreadable-test-data')
            continue
        for line_number, line in enumerate(lines, 1):
            for rule in sorted(_line_rules(line, source_file=path not in managed)):
                errors.append(f'{relative}:{line_number}: {rule}')
    return errors


def _validate_test_data_policy(root: Path) -> list[str]:
    """执行完整测试数据政策并返回稳定、脱敏的诊断。"""
    managed_data = _iter_managed_data(root)
    tracked, git_error = _git_tracked_files(root)
    if git_error:
        return [git_error]

    errors = [
        f'{path.relative_to(root).as_posix()}: untracked-test-data'
        for path in managed_data
        if path.relative_to(root).as_posix() not in tracked
    ]
    errors.extend(_scan_text_files(root, [*managed_data, *_iter_test_sources(root)]))
    return errors


def check(arguments: list[str]) -> CheckResult:
    """解析仓库根目录并返回测试数据政策的全部诊断。"""
    parser = argument_parser(description='检查测试数据可复现性与隐私边界')
    parser.add_argument('--repo-root', default=str(ROOT), help='Repository root')
    args = parser.parse_args(arguments)
    try:
        errors = _validate_test_data_policy(Path(args.repo_root).resolve())
    except (OSError, UnicodeError) as exc:
        return CheckResult.execution_failure(
            [f'无法完整读取测试数据检查输入: {exc}'], reason='input-unavailable'
        )
    if 'git-tracked-files-unavailable' in errors:
        return CheckResult.execution_failure(errors, reason='dependency-unavailable')
    if any(error.endswith('unreadable-test-data') for error in errors):
        return CheckResult.execution_failure(errors, reason='input-unavailable')
    return CheckResult.from_errors(errors)
