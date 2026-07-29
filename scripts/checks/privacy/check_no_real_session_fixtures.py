#!/usr/bin/env python3
"""本模块负责扫描受保护路径，检测是否包含真实 session fixture 或本地 home 路径。

失败条件（按 PROMPT 要求）：
- 文件路径或内容包含 .claude/projects、.codex/sessions 的真实 home 路径。
- 大 JSONL fixture 中出现明显真实 session 标记且未在 tests/fixtures/synthetic/ 下。
- 出现真实用户 home 路径（如开发者本机的绝对路径）。

允许：
- 文档中使用占位符 ~/.claude、~/.codex、~/.qoder。
- synthetic fixture 明确标注 synthetic。
- tests/fixtures/ 下使用合成用户名（如 test、demo）的 fixture。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from scripts.checks._framework import repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()


GATE_NAME = "noRealSessionFixtures"


SCAN_DIRS = [
    "tests/fixtures",
    "docs",
    ".qoder",
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

# 跳过构建产物目录（这些目录不应被扫描）。
_BUILD_DIR_PARTS = {
    "build",
    ".gradle",
    "node_modules",
    "__pycache__",
    ".local",
    "venv",
}


def fail(message: str) -> int:
    """输出单条 fixture 隐私失败原因并返回非零退出码。"""
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


def _safe_excerpt(line: str) -> str:
    """始终返回脱敏摘要，避免 Gate 诊断复述 session、prompt 或本地路径。"""
    return "<redacted>"


def _has_real_session_marker(line: str) -> str | None:
    """识别带真实 home 上下文的 session 路径，匹配时返回规则标识。"""
    for pat in _REAL_SESSION_PATH_RES:
        if pat.search(line):
            return pat.pattern
    return None


def _extract_users_username(line: str, match_start: int) -> str | None:
    after = line[match_start + len(_USERS_PREFIX) :]
    m = re.match(r"([^/\"'\s\\]+)", after)
    return m.group(1) if m else None


def _is_synthetic_username(username: str) -> bool:
    return username.lower() in _SYNTHETIC_USERNAMES


def _has_real_home_path(line: str) -> bool:
    """检查非合成用户的 home 绝对路径，并放行明确占位符。"""
    if _USERS_PREFIX not in line:
        return False

    # 明确占位符和泛化用户名不会指向真实机器。
    for pat in _PLACEHOLDER_PATTERNS:
        if pat.search(line):
            return False
    if re.search(re.escape(_U) + r"<", line):
        return False

    # 同一行可能出现多个 home 路径，必须逐个判断。
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


def _has_personal_username(line: str) -> bool:
    return _PERSONAL_USER in line.lower()


def _is_synthetic_dir(filepath: Path) -> bool:
    parts = filepath.parts
    return _SYNTHETIC_DIR_MARKER in parts


def _is_explicit_synthetic_jsonl(filepath: Path, text: str | None = None) -> bool:
    """仅当 JSONL 每条记录都显式声明 synthetic=true 时返回 True。"""
    if filepath.suffix != ".jsonl":
        return False
    try:
        source = text if text is not None else filepath.read_text(encoding="utf-8")
        records = [json.loads(line) for line in source.splitlines() if line]
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return bool(records) and all(record.get("synthetic") is True for record in records)


def _is_large_jsonl_violation(filepath: Path, explicit_synthetic: bool) -> bool:
    """判断大 JSONL 是否缺少 synthetic 目录或逐条显式声明。"""
    if filepath.suffix != ".jsonl":
        return False
    if _is_synthetic_dir(filepath) or explicit_synthetic:
        return False
    try:
        return filepath.stat().st_size > 10000
    except OSError:
        return False


def _is_build_artifact(filepath: Path) -> bool:
    return bool(set(filepath.parts) & _BUILD_DIR_PARTS)


def _looks_like_raw_session_content(line: str) -> bool:
    """以字段组合识别疑似原始 session 记录，降低单字段误报。"""
    if not line.lstrip().startswith(("{", "[")):
        return False
    marker_count = sum(1 for marker in _RAW_SESSION_JSON_MARKERS if marker in line)
    return marker_count >= 2


def _scan_file(filepath: Path) -> list[str]:
    """扫描单个 fixture 或文档并返回脱敏诊断；可疑内容按关闭式策略汇总。"""
    errors: list[str] = []
    if filepath.name in _SKIP_BASENAMES:
        return errors
    if _is_build_artifact(filepath):
        return errors

    rel = filepath.relative_to(ROOT)
    rel_str_check = str(rel)
    if any(rel_str_check.startswith(p) for p in _SKIP_DIR_PREFIXES):
        return errors

    # 先检查路径和文件级 JSONL 契约，再进入逐行内容规则。
    rel_str = str(rel)
    for pat in _REAL_SESSION_PATH_RES:
        if pat.search(rel_str) and not _is_synthetic_dir(filepath):
            errors.append(f"{rel}: 文件路径包含真实 session 标记")

    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        if _is_large_jsonl_violation(filepath, False):
            errors.append(f"{rel}: 大 JSONL fixture 不在允许目录下")
        return errors

    explicit_synthetic = _is_explicit_synthetic_jsonl(filepath, text)
    if _is_large_jsonl_violation(filepath, explicit_synthetic):
        errors.append(f"{rel}: 大 JSONL fixture 不在允许目录下")

    for lineno, line in enumerate(text.splitlines(), start=1):
        # 内容诊断始终使用脱敏摘要，避免 Gate 输出二次泄露。
        marker = _has_real_session_marker(line)
        if marker and not _is_synthetic_dir(filepath):
            errors.append(f"{rel}:{lineno}: 包含真实 session 路径标记: {_safe_excerpt(line)}")

        if _has_real_home_path(line):
            errors.append(f"{rel}:{lineno}: 包含真实 home 绝对路径: {_safe_excerpt(line)}")

        if _has_personal_username(line):
            errors.append(f"{rel}:{lineno}: 包含个人用户名: {_safe_excerpt(line)}")

        if (
            _looks_like_raw_session_content(line)
            and not _is_synthetic_dir(filepath)
            and not explicit_synthetic
        ):
            errors.append(
                f"{rel}:{lineno}: 包含疑似原始 session JSON/JSONL 内容: {_safe_excerpt(line)}"
            )

    return errors


def _iter_scan_files() -> list[Path]:
    """汇总配置声明的扫描文件并去重。"""
    files: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        """仅追加尚未收集的普通文件。"""
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


def main() -> int:
    """扫描真实 session fixture 与 home 泄露，任一可疑项即返回非零。"""

    all_errors: list[str] = []

    for filepath in _iter_scan_files():
        # 二进制文件不做文本启发式扫描，避免无意义解码与误报。
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
