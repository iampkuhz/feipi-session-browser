#!/usr/bin/env python3
"""扫描受保护路径，检测提交态中是否包含个人机器绝对路径。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_NAME = "noCommittedLocalPaths"

SCAN_DIRS = [
    ".claude",
    ".codex",
    ".qoder",
    ".agents",
    "skills",
    "harness",
    "scripts",
]
SCAN_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
]

# 扫描时跳过自身文件（避免自引用误报）
_SKIP_BASENAMES = {
    "check_no_committed_local_paths.py",
}

# /home/ 白名单模式：匹配这些模式的行不报告
_HOME_WHITELIST = [
    re.compile(r"/home/<"),              # 文档占位符 /home/<user>
    re.compile(r"/home/\<"),             # 文档占位符
    re.compile(r"/home/\$\{"),           # 文档占位符 /home/${USER}
    re.compile(r"/home/\$"),             # 文档占位符 /home/$USER
    re.compile(r"/home/your"),           # 文档说明 /home/your-username
    re.compile(r"/home/USER"),           # 文档说明
    re.compile(r"/home/\*"),             # 文档通配符
    re.compile(r"^#!"),                  # shebang
]

# Windows 盘符路径正则：大写盘符 + 反斜杠 + 典型路径字符
_WIN_DRIVE_RE = re.compile(r"[A-Z]:\\[A-Za-z]")

# 个人用户名关键字（拆分存储避免自引用误报）
_PERSONAL_PARTS = ["zhe", "han"]
PERSONAL_USERNAMES = ["".join(_PERSONAL_PARTS)]

# 路径模式前缀（拆分避免自引用误报）
_USERS_PREFIX = "/Users" + "/"
_HOME_PREFIX = "/home" + "/"


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        message: 用户可读错误信息。

    返回：
        进程退出码。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 检查行是否匹配 /home/ 白名单。
def _is_whitelisted_home(line: str) -> bool:
    """参数：
        line: 待检查的文本行。

    返回：
        是否在白名单中。
    """
    for pat in _HOME_WHITELIST:
        if pat.search(line):
            return True
    # Python 注释行中包含 /home/ 也放行
    stripped = line.lstrip()
    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    return False


# 扫描单个文件，返回发现的问题列表。
def _scan_file(filepath: Path) -> list[str]:
    """参数：
        filepath: 待扫描文件的绝对路径。

    返回：
        问题字符串列表。
    """
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
        if _USERS_PREFIX in line:
            errors.append(
                f"{rel}:{lineno}: 包含绝对路径 {_USERS_PREFIX}: "
                f"{line.strip()[:80]}"
            )

        # 检查 /home/ 路径（排除白名单）
        if _HOME_PREFIX in line and not _is_whitelisted_home(line):
            errors.append(
                f"{rel}:{lineno}: 包含可疑 {_HOME_PREFIX} 路径: "
                f"{line.strip()[:80]}"
            )

        # 检查 Windows 盘符路径（仅非 Python 源码文件检查，
        # Python 中 \\n \\s \\d 等转义大量存在）
        if filepath.suffix not in (".py",):
            if _WIN_DRIVE_RE.search(line):
                errors.append(
                    f"{rel}:{lineno}: 包含 Windows 绝对路径: "
                    f"{line.strip()[:80]}"
                )

        # 检查个人用户名（小写匹配）
        line_lower = line.lower()
        for username in PERSONAL_USERNAMES:
            if username in line_lower:
                errors.append(
                    f"{rel}:{lineno}: 包含个人用户名 '{username}': "
                    f"{line.strip()[:80]}"
                )
                break

    return errors


# 执行提交态本地路径扫描。
def main() -> int:
    """返回：
        进程退出码。
    """
    all_errors: list[str] = []

    # 扫描目录
    for scan_dir in SCAN_DIRS:
        dir_path = ROOT / scan_dir
        if not dir_path.is_dir():
            continue
        for filepath in sorted(dir_path.rglob("*")):
            if not filepath.is_file():
                continue
            # 跳过二进制文件和隐藏临时文件
            if filepath.suffix in (".pyc", ".pyo", ".sqlite", ".sqlite3"):
                continue
            all_errors.extend(_scan_file(filepath))

    # 扫描根文件
    for filename in SCAN_FILES:
        filepath = ROOT / filename
        if filepath.is_file():
            all_errors.extend(_scan_file(filepath))

    if all_errors:
        for err in all_errors:
            print(f"[{GATE_NAME}] FAIL: {err}")
        print(f"[{GATE_NAME}] FAIL: 共 {len(all_errors)} 处本地路径/用户名泄露")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
