"""检查受保护路径和测试文档中的类密钥内容。

这项检查避免疑似 token、授权头或私钥标记进入仓库。公开入口是 ``check(arguments)``，失败
表示发现必须移除、轮换或替换为合成值的可疑凭据。"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser, repository_root

ROOT = repository_root()


GATE_NAME = "secretLikeContent"


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


def _is_excluded_path(path: Path) -> bool:
    """判断路径是否属于扫描边界外的本地非提交目录。"""
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return True
    return any(relative == prefix or prefix in relative.parents for prefix in _SKIP_RELATIVE_DIRS)


def _is_safe_value(value: str) -> bool:
    """识别明确的占位符或测试值，避免把合成凭据当作真实密钥。"""
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


def _check_sk_token(line: str) -> str | None:
    """检查通用 sk- 长 token；明确的 dummy、test、example 值不报错。"""
    m = _SK_TOKEN_RE.search(line)
    if m:
        matched = m.group(0)
        # 前缀白名单只覆盖明确的合成值，其他长串保持可疑。
        if matched.lower().startswith("sk-dummy") or matched.lower().startswith("sk-test"):
            return None
        if matched.lower().startswith("sk-example"):
            return None
        return matched
    return None


def _check_anthropic_token(line: str) -> str | None:
    """检查 Anthropic 专属 token 前缀，匹配时返回脱敏类型。"""
    if _ANTHROPIC_TOKEN_RE.search(line):
        return "anthropic-token"
    return None


def _check_github_token(line: str) -> str | None:
    """检查 GitHub token 前缀，匹配时返回脱敏类型。"""
    if _GITHUB_TOKEN_RE.search(line):
        return "github-token"
    return None


def _check_bearer(line: str) -> str | None:
    """检查 Bearer 长串；仅返回有界前缀，避免诊断再次泄露完整 token。"""
    m = _BEARER_RE.search(line)
    if m:
        token = m.group(1)
        if _is_safe_value(token):
            return None
        if len(token) >= 10:
            return f"Bearer {token[:8]}..."
    return None


def _check_key_assignment(line: str) -> str | None:
    """检查密钥变量的长串赋值；仅返回有界摘要。"""
    m = _KEY_ASSIGN_RE.search(line)
    if m:
        value = m.group(1)
        if _is_safe_value(value):
            return None
        return f"<key>={value[:8]}..."
    return None


def _check_sensitive_marker(line: str) -> str | None:
    """检查敏感环境变量名或私钥块标记，匹配时返回脱敏类型。"""
    for marker in _SENSITIVE_MARKERS:
        if marker in line:
            return "sensitive-marker"
    return None


def _scan_file(filepath: Path) -> list[str]:
    """扫描单个文本文件并返回类密钥诊断；不可读取时由公开入口报告失败。"""
    errors: list[str] = []
    if filepath.name in _SKIP_BASENAMES:
        return errors

    text = filepath.read_text(encoding="utf-8")

    rel = filepath.relative_to(ROOT)

    for lineno, line in enumerate(text.splitlines(), start=1):
        # 注释常包含规则说明或合成示例，不作为凭据内容扫描。
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            continue

        # 先检查带供应商特征的 token，再检查通用授权头与赋值形式。
        sk_match = _check_sk_token(line)
        if sk_match:
            errors.append(f"{rel}:{lineno}: 检测到 sk- 开头的长 token: {sk_match[:20]}...")

        anthropic_match = _check_anthropic_token(line)
        if anthropic_match:
            errors.append(f"{rel}:{lineno}: 检测到 Anthropic token")

        github_match = _check_github_token(line)
        if github_match:
            errors.append(f"{rel}:{lineno}: 检测到 GitHub token")

        bearer_match = _check_bearer(line)
        if bearer_match:
            errors.append(f"{rel}:{lineno}: 检测到 Authorization Bearer 长串: {bearer_match}")

        key_match = _check_key_assignment(line)
        if key_match:
            errors.append(f"{rel}:{lineno}: 检测到密钥赋值长串: {key_match}")

        marker_match = _check_sensitive_marker(line)
        if marker_match:
            errors.append(f"{rel}:{lineno}: 检测到敏感环境变量或私钥标记")

    return errors


def check(arguments: list[str]) -> CheckResult:
    """解析统一入口参数并返回全部类密钥内容诊断。"""
    parser = argument_parser(description="检查受保护文件中的类密钥内容")
    parser.parse_args(arguments)
    all_errors: list[str] = []

    seen_files: set[Path] = set()
    try:
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
                # 先排除已知二进制，再以扩展名收紧文本扫描边界。
                if filepath.suffix in (
                    ".pyc",
                    ".pyo",
                    ".sqlite",
                    ".sqlite3",
                    ".class",
                    ".jar",
                ):
                    continue
                if filepath.suffix not in (
                    ".py",
                    ".md",
                    ".yaml",
                    ".yml",
                    ".json",
                    ".toml",
                    ".txt",
                    ".sh",
                    ".js",
                    ".ts",
                    ".java",
                    ".kts",
                    ".html",
                    ".css",
                    ".xml",
                    ".properties",
                    ".cfg",
                    ".ini",
                    ".conf",
                    "",
                ):
                    continue
                all_errors.extend(_scan_file(filepath))
    except (OSError, UnicodeError) as exc:
        return CheckResult.execution_failure(
            [f'无法完整扫描类密钥内容: {exc}'], reason='input-unavailable'
        )

    return CheckResult.from_errors(all_errors)
