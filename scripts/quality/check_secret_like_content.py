#!/usr/bin/env python3
"""轻量启发式：扫描受保护路径和测试文档，检测类密钥内容。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.quality._trigger import parse_changed_files, skip_if_not_triggered
GATE_NAME = "secretLikeContent"

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'tests/**', 'docs/**', 'java/**',
    'app-cli/**', 'src/**',
    '.claude/**', '.codex/**', '.qoder/**', '.agents/**',
    'skills/**', 'harness/**', 'scripts/**',
    'scripts/quality/check_secret_like_content.py',
]

SCAN_DIRS = [
    "tests",
    "docs",
    "java",
    ".claude",
    ".codex",
    ".qoder",
    ".agents",
    "skills",
    "harness",
    "harness/reports",
    "scripts",
]

# 白名单值（不视为真实密钥）。
_SAFE_VALUES = {
    "<placeholder>",
    "<redacted>",
    "redacted",
    "dummy",
    "dummy-token",
    "dummy-key",
    "example",
    "example-key",
    "test",
    "test-key",
    "your-api-key",
    "your-token",
    "<your-api-key>",
    "<your-token>",
    "<api-key>",
    "<token>",
    "<secret>",
    "changeme",
    "xxx",
    "todo",
    "fixme",
    "placeholder",
}

# sk- 开头的长 token 模式（至少 10 个字符的后续内容）。
_SK_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9]{10,}")

# Anthropic 专属 token 前缀（拆分避免 gate 自引用）。
_ANTHROPIC_TOKEN_RE = re.compile(r"sk-" r"ant-" r"[A-Za-z0-9_\-]{6,}")

# GitHub token 前缀（拆分避免 gate 自引用）。
_GITHUB_TOKEN_RE = re.compile(r"(?:gh" r"p_|github" r"_pat_)[A-Za-z0-9_]{12,}")

# Authorization: Bearer 后跟长串。
_BEARER_RE = re.compile(r"Authorization:\s*Bearer\s+(\S+)", re.IGNORECASE)

# api_key / access_token 后跟长串赋值。
_KEY_ASSIGN_RE = re.compile(
    r"(?:api_key|access_token|api_key|secret_key|auth_token)"
    r"\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?",
    re.IGNORECASE,
)

# 敏感环境变量名和私钥块标记（拆分避免 gate 自引用）。
_SENSITIVE_MARKERS = [
    "AWS" + "_SECRET" + "_ACCESS_KEY",
    "BEGIN " + "OPENSSH " + "PRIVATE KEY",
]

# 自身文件名跳过。
_SKIP_BASENAMES = {
    "check_secret_like_content.py",
}
_SKIP_RELATIVE_DIRS = {
    Path(".claude/worktrees"),
}


# 判断路径是否属于不应扫描的本地非提交目录。
def _is_excluded_path(path: Path) -> bool:
    """参数：
        path: 待判断的文件路径。

    返回：
        应排除时返回 true，否则返回 false。
    """
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return True
    return any(relative == prefix or prefix in relative.parents for prefix in _SKIP_RELATIVE_DIRS)


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        message: 用户可读错误信息。

    返回：
        进程退出码。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 检查值是否为安全的占位符。
def _is_safe_value(value: str) -> bool:
    """参数：
        value: 待检查的值。

    返回：
        值是否为安全占位符。
    """
    cleaned = value.strip().strip("'\"").lower()
    if cleaned in _SAFE_VALUES:
        return True
    if cleaned.startswith("<") and cleaned.endswith(">"):
        return True
    if cleaned.startswith("dummy") or cleaned.startswith("example"):
        return True
    if cleaned.startswith("test"):
        return True
    return False


# 检查单行是否包含 sk- 开头的长 token。
def _check_sk_token(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的 token 片段；无匹配返回 None。
    """
    m = _SK_TOKEN_RE.search(line)
    if m:
        matched = m.group(0)
        # 排除明显占位符
        if matched.lower().startswith("sk-dummy") or matched.lower().startswith("sk-test"):
            return None
        if matched.lower().startswith("sk-example"):
            return None
        return matched
    return None


# 检查单行是否包含 Anthropic token。
def _check_anthropic_token(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的 token 类型；无匹配返回 None。
    """
    if _ANTHROPIC_TOKEN_RE.search(line):
        return "anthropic-token"
    return None


# 检查单行是否包含 GitHub token。
def _check_github_token(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的 token 类型；无匹配返回 None。
    """
    if _GITHUB_TOKEN_RE.search(line):
        return "github-token"
    return None


# 检查单行是否包含 Authorization: Bearer 长串。
def _check_bearer(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的 token 片段；无匹配返回 None。
    """
    m = _BEARER_RE.search(line)
    if m:
        token = m.group(1)
        if _is_safe_value(token):
            return None
        if len(token) >= 10:
            return f"Bearer {token[:8]}..."
    return None


# 检查单行是否包含 api_key/access_token 赋值长串。
def _check_key_assignment(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的赋值片段；无匹配返回 None。
    """
    m = _KEY_ASSIGN_RE.search(line)
    if m:
        value = m.group(1)
        if _is_safe_value(value):
            return None
        return f"<key>={value[:8]}..."
    return None


# 检查单行是否包含敏感标记。
def _check_sensitive_marker(line: str) -> str | None:
    """参数：
        line: 待检查的文本行。

    返回：
        匹配到的敏感标记类型；无匹配返回 None。
    """
    for marker in _SENSITIVE_MARKERS:
        if marker in line:
            return "sensitive-marker"
    return None


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
        # 跳过注释行（Python / shell / JS）
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            continue

        # 检查 sk- token
        sk_match = _check_sk_token(line)
        if sk_match:
            errors.append(
                f"{rel}:{lineno}: 检测到 sk- 开头的长 token: "
                f"{sk_match[:20]}..."
            )

        anthropic_match = _check_anthropic_token(line)
        if anthropic_match:
            errors.append(f"{rel}:{lineno}: 检测到 Anthropic token")

        github_match = _check_github_token(line)
        if github_match:
            errors.append(f"{rel}:{lineno}: 检测到 GitHub token")

        # 检查 Bearer token
        bearer_match = _check_bearer(line)
        if bearer_match:
            errors.append(
                f"{rel}:{lineno}: 检测到 Authorization Bearer 长串: "
                f"{bearer_match}"
            )

        # 检查 key 赋值
        key_match = _check_key_assignment(line)
        if key_match:
            errors.append(
                f"{rel}:{lineno}: 检测到密钥赋值长串: {key_match}"
            )

        marker_match = _check_sensitive_marker(line)
        if marker_match:
            errors.append(f"{rel}:{lineno}: 检测到敏感环境变量或私钥标记")

    return errors


# 执行类密钥内容扫描。
def main() -> int:
    """返回：
        进程退出码。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    for i, arg in enumerate(sys.argv):
        if arg == '--changed-files' and i + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[i + 1])
            break
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    all_errors: list[str] = []

    seen_files: set[Path] = set()
    for scan_dir in SCAN_DIRS:
        dir_path = ROOT / scan_dir
        if not dir_path.is_dir():
            continue
        for filepath in sorted(dir_path.rglob("*")):
            if _is_excluded_path(filepath):
                continue
            if not filepath.is_file():
                continue
            if filepath in seen_files:
                continue
            seen_files.add(filepath)
            # 跳过二进制文件
            if filepath.suffix in (".pyc", ".pyo", ".sqlite", ".sqlite3", ".class", ".jar"):
                continue
            # 只检查文本文件
            if filepath.suffix not in (
                ".py", ".md", ".yaml", ".yml", ".json", ".toml",
                ".txt", ".sh", ".js", ".ts", ".java", ".kts",
                ".html", ".css", ".xml", ".properties", ".cfg",
                ".ini", ".conf", "",
            ):
                continue
            all_errors.extend(_scan_file(filepath))

    if all_errors:
        for err in all_errors:
            print(f"[{GATE_NAME}] FAIL: {err}")
        print(f"[{GATE_NAME}] FAIL: 共 {len(all_errors)} 处类密钥内容")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
