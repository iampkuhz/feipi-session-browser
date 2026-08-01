"""检查提交态受保护路径是否泄露个人机器绝对路径。

这项检查避免仓库保存本地用户名和 home 路径。公开入口是 ``check(arguments)``，失败表示发现
必须移除或脱敏的本地路径。"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

ROOT = repository_root()


GATE_NAME = "noCommittedLocalPaths"


SCAN_DIRS = [
    ".claude",
    ".codex",
    ".qoder",
    ".agents",
    "skills",
    "harness",
    "scripts",
    "tests/fixtures",
]
SCAN_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
]
SCAN_GLOBS = [
    "tests/test_*agent*runtime*.py",
]

# 扫描时跳过自身文件（避免自引用误报）
_SKIP_BASENAMES = {
    "check_no_committed_local_paths.py",
}
_SKIP_RELATIVE_DIRS = {
    Path(".claude/worktrees"),
}

# /home/ 白名单模式：匹配这些模式的行不报告
_HOME_WHITELIST = [
    re.compile(r"/home/<"),  # 文档占位符 /home/<user>
    re.compile(r"/home/\<"),  # 文档占位符
    re.compile(r"/home/\$\{"),  # 文档占位符 /home/${USER}
    re.compile(r"/home/\$"),  # 文档占位符 /home/$USER
    re.compile(r"/home/your"),  # 仅匹配文档中的示例 home 路径
    re.compile(r"/home/USER"),  # 文档说明
    re.compile(r"/home/\*"),  # 文档通配符
    re.compile(r"^#!"),  # 脚本的解释器声明
]

# Windows 盘符路径正则：大写盘符 + 反斜杠 + 典型路径字符
_WIN_DRIVE_RE = re.compile(r"[A-Z]:\\[A-Za-z]")

# 个人用户名关键字（拆分存储避免自引用误报）
_PERSONAL_PARTS = ["zhe", "han"]
PERSONAL_USERNAMES = ["".join(_PERSONAL_PARTS)]

# 路径模式前缀（拆分避免自引用误报）
_USERS_PREFIX = "/Users" + "/"
_HOME_PREFIX = "/home" + "/"

# fixture 中允许使用的合成用户名。
_SYNTHETIC_USERNAMES = {
    "test",
    "testuser",
    "demo",
    "user",
    "developer",
    "admin",
    "example",
    "your-username",
    "username",
    "dev",
}


def _safe_excerpt(line: str) -> str:
    """始终返回脱敏摘要，避免 Gate 诊断复述本地路径或 session 内容。"""
    return "<redacted>"


def _is_whitelisted_home(line: str) -> bool:
    """识别文档占位符和注释中的 /home/ 示例。"""
    for pat in _HOME_WHITELIST:
        if pat.search(line):
            return True
    # 注释用于解释检测规则，本身不作为提交态路径泄露。
    stripped = line.lstrip()
    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    return False


def _extract_username(line: str, prefix: str, match_start: int) -> str | None:
    after = line[match_start + len(prefix) :]
    m = re.match(r"([^/\"'\s\\]+)", after)
    return m.group(1) if m else None


def _is_synthetic_username(username: str) -> bool:
    return username.lower() in _SYNTHETIC_USERNAMES


def _has_real_user_path(line: str, prefix: str) -> bool:
    """逐个检查 home 前缀后的用户名，发现非合成用户即返回 True。"""
    idx = 0
    while True:
        pos = line.find(prefix, idx)
        if pos == -1:
            return False
        username = _extract_username(line, prefix, pos)
        if username and not _is_synthetic_username(username):
            return True
        idx = pos + len(prefix)


def _scan_file(filepath: Path) -> list[str]:
    """扫描单个 UTF-8 文件并返回脱敏的本地绝对路径诊断。"""
    errors: list[str] = []
    if filepath.name in _SKIP_BASENAMES:
        return errors
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return errors

    rel = filepath.relative_to(ROOT)

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Unix home 路径需结合合成用户名白名单判断。
        if _USERS_PREFIX in line and _has_real_user_path(line, _USERS_PREFIX):
            errors.append(f"{rel}:{lineno}: 包含绝对路径 {_USERS_PREFIX}: {_safe_excerpt(line)}")

        if (
            _HOME_PREFIX in line
            and not _is_whitelisted_home(line)
            and _has_real_user_path(line, _HOME_PREFIX)
        ):
            errors.append(f"{rel}:{lineno}: 包含可疑 {_HOME_PREFIX} 路径: {_safe_excerpt(line)}")

        # Python 正则和字符串中反斜杠密集，Windows 盘符规则仅用于其他文本。
        if filepath.suffix not in (".py",):
            if _WIN_DRIVE_RE.search(line):
                errors.append(f"{rel}:{lineno}: 包含 Windows 绝对路径: {_safe_excerpt(line)}")

        # 已知个人用户名独立兜底，避免没有完整 home 前缀时漏报。
        line_lower = line.lower()
        for username in PERSONAL_USERNAMES:
            if username in line_lower:
                errors.append(f"{rel}:{lineno}: 包含个人用户名 '{username}': {_safe_excerpt(line)}")
                break

    return errors


def _iter_scan_files() -> list[Path]:
    """汇总去重后的扫描文件，并阻止路径逃逸或进入本地 worktree。"""
    files: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        """仅接收仓库扫描边界内的普通文件，并保持首次出现顺序。"""
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            return
        if any(relative == prefix or prefix in relative.parents for prefix in _SKIP_RELATIVE_DIRS):
            return
        if path.is_file() and path not in seen:
            seen.add(path)
            files.append(path)

    for scan_dir in SCAN_DIRS:
        dir_path = ROOT / scan_dir
        if not dir_path.is_dir():
            continue
        for filepath in sorted(dir_path.rglob("*")):
            _add(filepath)

    for filename in SCAN_FILES:
        _add(ROOT / filename)

    for pattern in SCAN_GLOBS:
        for filepath in sorted(ROOT.glob(pattern)):
            _add(filepath)

    return files


def check(arguments: list[str]) -> CheckResult:
    """解析统一入口参数并返回全部本地路径泄露诊断。"""
    parser = argument_parser(description="检查提交态本地绝对路径")
    parser.parse_args(arguments)
    return CheckResult.from_errors(
        error for path in _iter_scan_files() for error in _scan_file(path)
    )
