#!/usr/bin/env python3
"""仓库瘦身回归门禁。

在 repo slimming sprint 之后，防止后续 agent 重新引入：
1. 历史版本注释（HIFI vN、DEPRECATED Tn、migrated Task n 等）
2. harness/ 中的已删除/changelog/历史日志引用
3. 移动设备/平板视口支持
4. 无实际作用的兼容垫片（只有注释的 CSS/JS、未引用的 display:none）
"""
from __future__ import annotations

from pathlib import Path
import re


# ── Rule 1: no-historical-version-comments ────────────────────────────

# 禁止的历史版本注释模式
HISTORICAL_VERSION_PATTERNS = [
    re.compile(r"HIFI\s+v\d+", re.IGNORECASE),
    re.compile(r"session_browser_hifi_v", re.IGNORECASE),
    re.compile(r"session-detail-payload-v", re.IGNORECASE),
    re.compile(r"DEPRECATED\s+T\d+", re.IGNORECASE),
    re.compile(r"migrated\s+Task\s+\d+", re.IGNORECASE),
]


def check_no_historical_version_comments(
    files: list[Path],
) -> tuple[list[str], list[str]]:
    """扫描文件中的历史版本注释模式。

    当前仓库中仍存在少量历史残留（sessions-list.css 等），
    因此采用 WARN 策略，不 BLOCK。如果未来清零，可升级为 BLOCK。
    """
    errors: list[str] = []
    warnings: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pattern in HISTORICAL_VERSION_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                warnings.append(
                    f"{path}: 发现历史版本注释模式 "
                    f"'{matches[0]}'（共 {len(matches)} 处），"
                    f"应清理并禁止新增（rule: no-historical-version-comments）。"
                )
    return errors, warnings


# ── Rule 2: harness-current-state-only ────────────────────────────────

# harness/ 中禁止出现的模式（描述当前状态即可，不需要历史痕迹）
HARNESS_FORBIDDEN_PATTERNS = [
    (re.compile(r"deleted", re.IGNORECASE), "deleted"),
    (re.compile(r"已删除", re.IGNORECASE), "已删除"),
    (re.compile(r"\bchangelog\b", re.IGNORECASE), "changelog"),
    (re.compile(r"\.agent/quality", re.IGNORECASE), ".agent/quality"),
    # tmp/agent_logs/MMDD 是历史日志路径引用，应使用 current 或动态路径
    (re.compile(r"tmp/agent_logs/MMDD", re.IGNORECASE), "tmp/agent_logs/MMDD"),
]

# 允许出现 forbidden pattern 的上下文关键词（如文档说明）
HARNESS_ALLOWED_CONTEXT = [
    # 如果是在描述「不允许删除」或「不存在」等语境中，可豁免
    re.compile(r"禁止.*deleted", re.IGNORECASE),
    re.compile(r"不存在.*deleted", re.IGNORECASE),
    re.compile(r"no.*deleted", re.IGNORECASE),
]


def _line_has_allowed_context(line: str) -> bool:
    """检查一行是否包含允许该 forbidden pattern 出现的上下文。"""
    for ctx in HARNESS_ALLOWED_CONTEXT:
        if ctx.search(line):
            return True
    return False


def check_harness_current_state(
    harness_files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查 harness/ 中是否包含历史痕迹。

    由于 harness/README.md 等文档中仍有 tmp/agent_logs/MMDD 的文档引用
    （描述日志目录格式），此处使用 WARN。真正的 BLOCK 留给新增内容。
    """
    errors: list[str] = []
    warnings: list[str] = []
    for path in harness_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pattern, label in HARNESS_FORBIDDEN_PATTERNS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    # 检查上下文豁免
                    if _line_has_allowed_context(line):
                        continue
                    warnings.append(
                        f"{path}:{lineno}: harness 中出现 '{label}' "
                        f"（rule: harness-current-state-only），"
                        f"harness 应只描述当前状态。"
                    )
    return errors, warnings


# ── Rule 3: supported-viewports-only ─────────────────────────────────

# 禁止的移动/平板视口模式
MOBILE_VIEWPORT_PATTERNS = [
    re.compile(r"max-width\s*:\s*767px", re.IGNORECASE),
    re.compile(r"max-width\s*:\s*768px", re.IGNORECASE),
    re.compile(r"max-width\s*:\s*820px", re.IGNORECASE),
    re.compile(r"min-width\s*:\s*768px.*max-width\s*:\s*1024px", re.IGNORECASE),
    # 通用移动/平板关键词在 @media 上下文中
    re.compile(r"@media[^{]*(?:mobile|tablet|ipad)", re.IGNORECASE),
]

# 允许的桌面视口宽度（出现在 @media 中是 OK 的）
ALLOWED_DESKTOP_VIEWPORTS = {1400, 1440, 1512, 1920, 2560}


def _is_allowed_viewport(line: str) -> bool:
    """检查是否为允许的桌面视口 breakpoint。"""
    for vw in ALLOWED_DESKTOP_VIEWPORTS:
        if f"{vw}px" in line:
            return True
    return False


def check_supported_viewports_only(
    css_files: list[Path],
    js_files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查 CSS/JS 中是否引入移动/平板视口支持。

    当前仓库无此类引用，直接 BLOCK。
    """
    errors: list[str] = []
    warnings: list[str] = []
    all_files = css_files + js_files
    for path in all_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            # 跳过注释行中的提及（仅告警，不 block）
            stripped = line.strip()
            if stripped.startswith("/*") or stripped.startswith("*") or stripped.startswith("//"):
                continue
            # 检查禁止的视口模式
            for pattern in MOBILE_VIEWPORT_PATTERNS:
                if pattern.search(line):
                    if _is_allowed_viewport(line):
                        continue
                    errors.append(
                        f"{path}:{lineno}: 禁止移动/平板视口支持 "
                        f"（rule: supported-viewports-only），"
                        f"仅支持桌面端视口。"
                    )
    return errors, warnings


# ── Rule 4: no-dead-compat-shim ──────────────────────────────────────


def _css_has_only_comments_or_empty(text: str) -> bool:
    """去掉注释和空白后，判断是否没有有效 CSS rule。"""
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    stripped = stripped.strip()
    return not stripped or ("{" not in stripped and "}" not in stripped)


def _js_is_only_comments_or_empty(text: str) -> bool:
    """去掉注释后，判断是否没有有效 JS 代码。"""
    stripped = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
    # 去掉空白行
    lines = [l for l in stripped.splitlines() if l.strip()]
    return len(lines) == 0


def check_no_dead_compat_shim(
    css_files: list[Path],
    js_files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查 CSS/JS 文件是否只有注释或无实际作用。

    同时检查 display:none 模式：如果有选择器只在 display:none 中
    被引用，且没有其他规则引用它，这是死兼容垫片。

    BLOCK：只有注释/空白的 CSS/JS 文件。
    WARN：display:none 用于保持未引用的旧选择器。
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check 4a: only-comments-or-empty files
    for path in css_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if _css_has_only_comments_or_empty(text):
            errors.append(
                f"{path}: 死 CSS 文件（只有注释或空白，"
                f"无有效 rule，rule: no-dead-compat-shim）。"
            )

    for path in js_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if _js_is_only_comments_or_empty(text):
            errors.append(
                f"{path}: 死 JS 文件（只有注释或空白，"
                f"无有效代码，rule: no-dead-compat-shim）。"
            )

    # Check 4b: display:none on selectors that look like legacy aliases
    # Only warn, not block — display:none is a legitimate CSS pattern.
    legacy_like_pattern = re.compile(
        r"\.(?:old[-_]?|legacy[-_]?|deprecated[-_]?|compat[-_]?|v\d[-_]?)",
        re.IGNORECASE,
    )
    for path in css_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "display" in line and "none" in line:
                # Check if the preceding selector looks like a legacy shim
                # Look backwards for the selector
                all_lines = text.splitlines()
                selector_lines = []
                for prev_idx in range(lineno - 2, max(lineno - 11, -1), -1):
                    if prev_idx < 0 or prev_idx >= len(all_lines):
                        continue
                    prev_line = all_lines[prev_idx]
                    selector_lines.append(prev_line)
                    if "{" in prev_line:
                        break

                selector_text = " ".join(selector_lines)
                if legacy_like_pattern.search(selector_text):
                    warnings.append(
                        f"{path}:{lineno}: display:none 用于疑似兼容垫片选择器 "
                        f"（rule: no-dead-compat-shim），"
                        f"确认该选择器是否仍有必要。"
                    )

    return errors, warnings


# ── Composite check ────────────────────────────────────────────────────


def check_repo_slimming(repo_root: Path) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。

    综合运行所有瘦身回归门禁。
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Rule 1: no-historical-version-comments
    # Scan all tracked text files in the repo
    all_text_files: list[Path] = []
    for ext in ("*.css", "*.js", "*.html", "*.py", "*.md", "*.sh", "*.yaml", "*.json", "*.txt"):
        all_text_files.extend(repo_root.rglob(ext))
    # Exclude build/cache dirs and the check file itself (patterns in regex source)
    exclude_dirs = {".git", "node_modules", "__pycache__", ".pytest_cache", "tmp", ".mypy_cache", "dist", "venv", ".venv"}
    check_self = "repo_slimming_contract_check.py"
    filtered_files = []
    for f in all_text_files:
        if any(ex in f.parts for ex in exclude_dirs):
            continue
        if f.name == check_self:
            continue  # regex source strings match own file
        filtered_files.append(f)
    e, w = check_no_historical_version_comments(filtered_files)
    errors.extend(e)
    warnings.extend(w)

    # Rule 2: harness-current-state-only
    harness_dir = repo_root / "harness"
    if harness_dir.exists():
        harness_files = list(harness_dir.rglob("*.md")) + list(harness_dir.rglob("*.yaml"))
        e, w = check_harness_current_state(harness_files)
        errors.extend(e)
        warnings.extend(w)

    # Rule 3: supported-viewports-only
    static = repo_root / "src/session_browser/web/static"
    if static.exists():
        css_files = list(static.rglob("*.css"))
        js_files = list(static.rglob("*.js"))
        e, w = check_supported_viewports_only(css_files, js_files)
        errors.extend(e)
        warnings.extend(w)

        # Rule 4: no-dead-compat-shim
        e, w = check_no_dead_compat_shim(css_files, js_files)
        errors.extend(e)
        warnings.extend(w)

    return errors, warnings


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> int:
    errors, warnings = check_repo_slimming(Path.cwd())
    for item in warnings:
        print(f"[WARN] {item}")
    if errors:
        for item in errors:
            print(f"[BLOCK] {item}")
        return 1
    print("repo slimming contract PASS" if not warnings else "repo slimming contract PASS (with warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
