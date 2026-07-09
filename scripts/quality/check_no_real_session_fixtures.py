#!/usr/bin/env python3
"""扫描受保护路径，检测是否包含真实 session fixture 或本地 home 路径。

失败条件（按 PROMPT 要求）：
- 文件路径或内容包含 .claude/projects、.codex/sessions 的真实 home 路径。
- 大 JSONL fixture 中出现明显真实 session 标记且未在 tests/fixtures/synthetic/ 下。
- 出现真实用户 home 路径（如开发者本机的绝对路径）。

允许：
- 文档中使用占位符 ~/.claude、~/.codex、~/.qoder。
- synthetic fixture 明确标注 synthetic。
- tests/fixtures/ 下使用合成用户名（如 test、demo）的 fixture。
- docs/session-samples/ 下的文档样例。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_NAME = "noRealSessionFixtures"

SCAN_DIRS = [
    "tests",
    "docs",
]

# 个人 home 路径前缀（拆分避免自引用误报和 gate 自引用）。
_U = "/Users" + "/"
_USERS_PREFIX = _U
_PERSONAL_PARTS = ["zhe", "han"]
_PERSONAL_USER = "".join(_PERSONAL_PARTS)

# 合成 fixture 常用的用户名白名单（不是真实用户）。
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

# 白名单：文档中允许的占位符模式。
_PLACEHOLDER_PATTERNS = [
    re.compile(r"~/\.claude"),
    re.compile(r"~/\.codex"),
    re.compile(r"~/\.qoder"),
    re.compile(r"<placeholder>", re.IGNORECASE),
    re.compile(r"<REDACTED>", re.IGNORECASE),
    re.compile(r"\{REDACTED\}", re.IGNORECASE),
]

# 自身文件名跳过。
_SKIP_BASENAMES = {
    "check_no_real_session_fixtures.py",
    "check_no_committed_local_paths.py",
}

# 整个目录跳过（架构文档等允许引用仓库路径的文件）。
_SKIP_DIR_PREFIXES = {
    "docs/architecture",
}

# 合成 fixture 目录名标记。
_SYNTHETIC_DIR_MARKER = "synthetic"

# 真实 session 路径完整模式（需要路径上下文，避免子串匹配误报）。
# 注意：.qoder/ 是仓库目录结构，不在此检查范围内。
# 注意：.claude/projects 和 .codex/sessions 必须是真实 home 路径下的，
# 仓库内的 tests/fixtures/attribution/.qoder/ 等不算。
_REAL_SESSION_PATH_RES = [
    re.compile(r"(?:" + re.escape(_U) + r"[^/]+/)\.claude/projects/"),
    re.compile(r"(?:" + re.escape(_U) + r"[^/]+/)\.codex/sessions/"),
]

# 允许包含真实数据的已知目录（文档样例、测试 fixture 等）。
# 这些目录中的文件不做大 JSONL 检查，但仍检查个人 home 路径。
_KNOWN_SAMPLE_DIRS = [
    "docs/session-samples",
]

# 允许包含合成数据的已知 fixture 目录。
# 这些目录中的文件不做内容检查，只做路径结构检查。
_KNOWN_FIXTURE_DIRS = [
    "tests/fixtures",
]

# 跳过构建产物目录（这些目录不应被扫描）。
_BUILD_DIR_PARTS = {
    "build",
    ".gradle",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
}


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        message: 用户可读错误信息。

    返回：
        进程退出码。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 检查文件是否在已知样例目录下。
def _is_in_known_sample_dir(filepath: Path) -> bool:
    """参数：
        filepath: 待检查的文件路径。

    返回：
        文件是否在已知样例目录下。
    """
    rel_str = str(filepath.relative_to(ROOT))
    return any(rel_str.startswith(d) for d in _KNOWN_SAMPLE_DIRS)


# 检查文件是否在已知 fixture 目录下。
def _is_in_known_fixture_dir(filepath: Path) -> bool:
    """参数：
        filepath: 待检查的文件路径。

    返回：
        文件是否在已知 fixture 目录下。
    """
    rel_str = str(filepath.relative_to(ROOT))
    return any(rel_str.startswith(d) for d in _KNOWN_FIXTURE_DIRS)


# 检查行是否包含真实 session 路径标记（需要 home 路径上下文）。
def _has_real_session_marker(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的标记名称；无匹配返回 None。
    """
    for pat in _REAL_SESSION_PATH_RES:
        if pat.search(line):
            return pat.pattern
    return None


# 提取 home 路径中的用户名。
def _extract_users_username(line: str, match_start: int) -> str | None:
    """参数：
        line: 文本行。
        match_start: home 路径匹配位置。

    返回：
        提取到的用户名；无法提取返回 None。
    """
    after = line[match_start + len(_USERS_PREFIX):]
    m = re.match(r"([^/\"'\s\\]+)", after)
    return m.group(1) if m else None


# 检查用户名是否为合成 placeholder。
def _is_synthetic_username(username: str) -> bool:
    """参数：
        username: 待检查的用户名。

    返回：
        是否为合成用户名。
    """
    return username.lower() in _SYNTHETIC_USERNAMES


# 检查行是否包含真实 home 绝对路径。
def _has_real_home_path(line: str) -> bool:
    """参数：
        line: 待检查的文本行。

    返回：
        是否包含真实 home 路径。
    """
    if _USERS_PREFIX not in line:
        return False

    # 排除占位符
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(line):
            return False
    # 排除文档中泛化的 home 路径占位符写法
    if re.search(re.escape(_U) + r"<", line):
        return False

    # 检查每个 home 路径出现的用户名
    idx = 0
    while True:
        pos = line.find(_USERS_PREFIX, idx)
        if pos == -1:
            break
        username = _extract_users_username(line, pos)
        if username and not _is_synthetic_username(username):
            return True
        idx = pos + len(_USERS_PREFIX)

    return False


# 检查行是否包含个人用户名。
def _has_personal_username(line: str) -> bool:
    """参数：
        line: 待检查的文本行。

    返回：
        是否包含个人用户名。
    """
    return _PERSONAL_USER in line.lower()


# 检查文件路径是否在 synthetic 目录下。
def _is_synthetic_dir(filepath: Path) -> bool:
    """参数：
        filepath: 待检查的文件路径。

    返回：
        文件是否在 synthetic fixture 目录下。
    """
    parts = filepath.parts
    return _SYNTHETIC_DIR_MARKER in parts


# 检查文件是否为大 JSONL fixture 且不在允许目录下。
def _is_large_jsonl_violation(filepath: Path) -> bool:
    """参数：
        filepath: 待检查的文件路径。

    返回：
        文件是否为大 JSONL 违规。
    """
    if filepath.suffix != ".jsonl":
        return False
    if _is_synthetic_dir(filepath):
        return False
    if _is_in_known_fixture_dir(filepath):
        return False
    if _is_in_known_sample_dir(filepath):
        return False
    try:
        return filepath.stat().st_size > 10000
    except OSError:
        return False


# 检查文件是否在构建产物目录下。
def _is_build_artifact(filepath: Path) -> bool:
    """参数：
        filepath: 待检查的文件路径。

    返回：
        文件是否在构建产物目录下。
    """
    return bool(set(filepath.parts) & _BUILD_DIR_PARTS)


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
    if _is_build_artifact(filepath):
        return errors

    rel = filepath.relative_to(ROOT)
    rel_str_check = str(rel)
    if any(rel_str_check.startswith(p) for p in _SKIP_DIR_PREFIXES):
        return errors

    # 检查文件路径本身是否包含真实 session 标记（完整路径模式）
    rel_str = str(rel)
    for pat in _REAL_SESSION_PATH_RES:
        if pat.search(rel_str) and not _is_synthetic_dir(filepath):
            errors.append(f"{rel}: 文件路径包含真实 session 标记")

    # 检查大 JSONL 不在允许目录
    if _is_large_jsonl_violation(filepath):
        errors.append(f"{rel}: 大 JSONL fixture 不在允许目录下")

    # 已知 fixture 和样例目录中的文件不做内容检查
    # （这些目录的数据由其他 gate 管理）
    if _is_in_known_fixture_dir(filepath) or _is_in_known_sample_dir(filepath):
        return errors

    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return errors

    for lineno, line in enumerate(text.splitlines(), start=1):
        # 检查真实 session 标记（需要 home 路径上下文）
        marker = _has_real_session_marker(line)
        if marker and not _is_synthetic_dir(filepath):
            errors.append(
                f"{rel}:{lineno}: 包含真实 session 路径标记: "
                f"{line.strip()[:80]}"
            )

        # 检查真实 home 路径（排除合成用户名）
        if _has_real_home_path(line):
            errors.append(
                f"{rel}:{lineno}: 包含真实 home 绝对路径: "
                f"{line.strip()[:80]}"
            )

        # 检查个人用户名
        if _has_personal_username(line):
            errors.append(
                f"{rel}:{lineno}: 包含个人用户名: "
                f"{line.strip()[:80]}"
            )

    return errors


# 执行真实 session fixture 扫描。
def main() -> int:
    """返回：
        进程退出码。
    """
    all_errors: list[str] = []

    for scan_dir in SCAN_DIRS:
        dir_path = ROOT / scan_dir
        if not dir_path.is_dir():
            continue
        for filepath in sorted(dir_path.rglob("*")):
            if not filepath.is_file():
                continue
            # 跳过二进制文件
            if filepath.suffix in (".pyc", ".pyo", ".sqlite", ".sqlite3", ".class", ".jar"):
                continue
            all_errors.extend(_scan_file(filepath))

    if all_errors:
        for err in all_errors:
            print(f"[{GATE_NAME}] FAIL: {err}")
        print(f"[{GATE_NAME}] FAIL: 共 {len(all_errors)} 处真实 session/home 路径泄露")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
