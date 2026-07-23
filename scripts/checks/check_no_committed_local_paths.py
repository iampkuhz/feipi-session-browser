#!/usr/bin/env python3
"""本模块负责扫描受保护路径，检测提交态中是否包含个人机器绝对路径。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.checks._framework import repository_root

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


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """输出 FAIL 并返回非 0。"""
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 返回安全摘要，避免 gate 输出原始本地路径或 session 内容。
def _safe_excerpt(line: str) -> str:
    return "<redacted>"


# 检查行是否匹配 /home/ 白名单。
def _is_whitelisted_home(line: str) -> bool:
    for pat in _HOME_WHITELIST:
        if pat.search(line):
            return True
    # Python 注释行中包含 /home/ 也放行
    stripped = line.lstrip()
    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    return False


# 提取 home 路径中的用户名。
def _extract_username(line: str, prefix: str, match_start: int) -> str | None:
    after = line[match_start + len(prefix) :]
    m = re.match(r"([^/\"'\s\\]+)", after)
    return m.group(1) if m else None


# 检查用户名是否为合成 placeholder。
def _is_synthetic_username(username: str) -> bool:
    return username.lower() in _SYNTHETIC_USERNAMES


# 检查行是否包含非合成的本地 home 绝对路径。
def _has_real_user_path(line: str, prefix: str) -> bool:
    idx = 0
    while True:
        pos = line.find(prefix, idx)
        if pos == -1:
            return False
        username = _extract_username(line, prefix, pos)
        if username and not _is_synthetic_username(username):
            return True
        idx = pos + len(prefix)


# 扫描单个文件，返回发现的问题列表。
def _scan_file(filepath: Path) -> list[str]:
    errors: list[str] = []
    if filepath.name in _SKIP_BASENAMES:
        return errors
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return errors

    rel = filepath.relative_to(ROOT)

    for lineno, line in enumerate(text.splitlines(), start=1):
        # 检查 /Users/ 路径
        if _USERS_PREFIX in line and _has_real_user_path(line, _USERS_PREFIX):
            errors.append(f"{rel}:{lineno}: 包含绝对路径 {_USERS_PREFIX}: {_safe_excerpt(line)}")

        # 检查 /home/ 路径（排除白名单）
        if (
            _HOME_PREFIX in line
            and not _is_whitelisted_home(line)
            and _has_real_user_path(line, _HOME_PREFIX)
        ):
            errors.append(f"{rel}:{lineno}: 包含可疑 {_HOME_PREFIX} 路径: {_safe_excerpt(line)}")

        # 检查 Windows 盘符路径（仅非 Python 源码文件检查，
        # Python 中 \\n \\s \\d 等转义大量存在）
        if filepath.suffix not in (".py",):
            if _WIN_DRIVE_RE.search(line):
                errors.append(f"{rel}:{lineno}: 包含 Windows 绝对路径: {_safe_excerpt(line)}")

        # 检查个人用户名（小写匹配）
        line_lower = line.lower()
        for username in PERSONAL_USERNAMES:
            if username in line_lower:
                errors.append(f"{rel}:{lineno}: 包含个人用户名 '{username}': {_safe_excerpt(line)}")
                break

    return errors


# 迭代门禁扫描文件。
def _iter_scan_files() -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        """执行 `add` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
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
            add(filepath)

    for filename in SCAN_FILES:
        add(ROOT / filename)

    for pattern in SCAN_GLOBS:
        for filepath in sorted(ROOT.glob(pattern)):
            add(filepath)

    return files


# 执行提交态本地路径扫描。
def check_local_paths() -> list[str]:
    """返回所有已跟踪治理路径中的本地绝对路径诊断。"""
    return [error for path in _iter_scan_files() for error in _scan_file(path)]
