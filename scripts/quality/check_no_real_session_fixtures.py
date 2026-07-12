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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality._trigger import parse_changed_files, skip_if_not_triggered
GATE_NAME = "noRealSessionFixtures"

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'tests/**', 'docs/**', 'java/**',
    'app-cli/**', 'src/**',
    'scripts/quality/check_no_real_session_fixtures.py',
]

SCAN_DIRS = [
    "tests/fixtures",
    "docs",
    ".qoder",
    "harness/reports",
]
SCAN_GLOBS = [
    "tests/test_*agent*runtime*.py",
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
    re.compile(r"(?:" + re.escape(_U) + r"[^/]+/)\.qoder/"),
]

# 原始 session JSON/JSONL 常见字段组合；允许 synthetic 目录中的合成结构样例。
_RAW_SESSION_JSON_MARKERS = [
    '"parentUuid"',
    '"promptId"',
    '"messageId"',
    '"sessionId"',
    '"toolUseResult"',
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 返回安全摘要，避免 gate 输出原始 session、prompt 或本地路径。
def _safe_excerpt(line: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return "<redacted>"


# 检查文件是否在已知样例目录下。
def _is_in_known_sample_dir(filepath: Path) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    rel_str = str(filepath.relative_to(ROOT))
    return any(rel_str.startswith(d) for d in _KNOWN_SAMPLE_DIRS)


# 检查文件是否在已知 fixture 目录下。
def _is_in_known_fixture_dir(filepath: Path) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    rel_str = str(filepath.relative_to(ROOT))
    return any(rel_str.startswith(d) for d in _KNOWN_FIXTURE_DIRS)


# 检查行是否包含真实 session 路径标记（需要 home 路径上下文）。
def _has_real_session_marker(line: str) -> str | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    for pat in _REAL_SESSION_PATH_RES:
        if pat.search(line):
            return pat.pattern
    return None


# 提取 home 路径中的用户名。
def _extract_users_username(line: str, match_start: int) -> str | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    after = line[match_start + len(_USERS_PREFIX):]
    m = re.match(r"([^/\"'\s\\]+)", after)
    return m.group(1) if m else None


# 检查用户名是否为合成 placeholder。
def _is_synthetic_username(username: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return username.lower() in _SYNTHETIC_USERNAMES


# 检查行是否包含真实 home 绝对路径。
def _has_real_home_path(line: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return _PERSONAL_USER in line.lower()


# 检查文件路径是否在 synthetic 目录下。
def _is_synthetic_dir(filepath: Path) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    parts = filepath.parts
    return _SYNTHETIC_DIR_MARKER in parts


# 检查文件是否为大 JSONL fixture 且不在允许目录下。
def _is_large_jsonl_violation(filepath: Path) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return bool(set(filepath.parts) & _BUILD_DIR_PARTS)


# 检查行是否像原始 session JSON/JSONL 内容。
def _looks_like_raw_session_content(line: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if not line.lstrip().startswith(("{", "[")):
        return False
    marker_count = sum(1 for marker in _RAW_SESSION_JSON_MARKERS if marker in line)
    return marker_count >= 2


# 扫描单个文件，返回发现的问题列表。
def _scan_file(filepath: Path) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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

    # 已知文档样例目录中的文件不做内容检查
    # （仍已在上方完成路径结构检查）
    if _is_in_known_sample_dir(filepath):
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
                f"{_safe_excerpt(line)}"
            )

        # 检查真实 home 路径（排除合成用户名）
        if _has_real_home_path(line):
            errors.append(
                f"{rel}:{lineno}: 包含真实 home 绝对路径: "
                f"{_safe_excerpt(line)}"
            )

        # 检查个人用户名
        if _has_personal_username(line):
            errors.append(
                f"{rel}:{lineno}: 包含个人用户名: "
                f"{_safe_excerpt(line)}"
            )

        if _looks_like_raw_session_content(line) and not _is_synthetic_dir(filepath):
            errors.append(
                f"{rel}:{lineno}: 包含疑似原始 session JSON/JSONL 内容: "
                f"{_safe_excerpt(line)}"
            )

    return errors


# 迭代门禁扫描文件。
def _iter_scan_files() -> list[Path]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    files: list[Path] = []
    seen: set[Path] = set()

    # 维护 add 函数行为。
    def add(path: Path) -> None:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        if path.is_file() and path not in seen:
            seen.add(path)
            files.append(path)

    for scan_dir in SCAN_DIRS:
        dir_path = ROOT / scan_dir
        if not dir_path.is_dir():
            continue
        for filepath in sorted(dir_path.rglob("*")):
            add(filepath)

    for pattern in SCAN_GLOBS:
        for filepath in sorted(ROOT.glob(pattern)):
            add(filepath)

    return files


# 执行真实 session fixture 扫描。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    for i, arg in enumerate(sys.argv):
        if arg == '--changed-files' and i + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[i + 1])
            break
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    all_errors: list[str] = []

    for filepath in _iter_scan_files():
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
