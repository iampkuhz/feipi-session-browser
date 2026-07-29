#!/usr/bin/env python3
"""本模块负责仓库瘦身回归门禁。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# 当前态文档和源码中禁止保留的历史版本标记。
HISTORICAL_VERSION_PATTERNS = [
    re.compile(r'HIFI\s+v\d+', re.IGNORECASE),
    re.compile(r'session_browser_hifi_v', re.IGNORECASE),
    re.compile(r'session-detail-payload-v', re.IGNORECASE),
    re.compile(r'DEPRECATED\s+T\d+', re.IGNORECASE),
    re.compile(r'migrated\s+Task\s+\d+', re.IGNORECASE),
]


def check_no_historical_version_comments(
    files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查历史版本标记；仓库只描述当前状态，命中即阻断。"""
    errors: list[str] = []
    warnings: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for pattern in HISTORICAL_VERSION_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                errors.append(
                    f'{path}: 发现历史版本注释模式 '
                    f"'{matches[0]}'（共 {len(matches)} 处），"
                    f'必须清理（rule: no-historical-version-comments）。'
                )
    return errors, warnings


# Harness 只描述当前可执行状态，不保留迁移或删除历史。
HARNESS_FORBIDDEN_PATTERNS = [
    (re.compile(r'deleted', re.IGNORECASE), 'deleted'),
    (re.compile(r'已删除', re.IGNORECASE), '已删除'),
    (re.compile(r'\bchangelog\b', re.IGNORECASE), 'changelog'),
    (re.compile(r'\.agent/quality', re.IGNORECASE), '.agent/quality'),
    # 固定日期日志路径会迅速失效，应使用当前或动态路径。
    (re.compile(r'tmp/agent_logs/MMDD', re.IGNORECASE), 'tmp/agent_logs/MMDD'),
]

# 否定或规则说明语境不代表维护历史状态，允许保留。
HARNESS_ALLOWED_CONTEXT = [
    re.compile(r'禁止.*deleted', re.IGNORECASE),
    re.compile(r'不存在.*deleted', re.IGNORECASE),
    re.compile(r'no.*deleted', re.IGNORECASE),
]


def _line_has_allowed_context(line: str) -> bool:
    """判断禁用词是否处于明确允许的否定或规则说明语境。"""
    for ctx in HARNESS_ALLOWED_CONTEXT:
        if ctx.search(line):
            return True
    return False


def check_harness_current_state(
    harness_files: list[Path],
) -> tuple[list[str], list[str]]:
    """检查 Harness 是否只描述当前可执行状态；非豁免命中即阻断。"""
    errors: list[str] = []
    warnings: list[str] = []
    for path in harness_files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for pattern, label in HARNESS_FORBIDDEN_PATTERNS:
            for lineno, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    # 先识别否定语境，避免规则说明自身触发门禁。
                    if _line_has_allowed_context(line):
                        continue
                    errors.append(
                        f"{path}:{lineno}: harness 中出现 '{label}' "
                        f'（rule: harness-current-state-only），'
                        f'harness 应只描述当前状态。'
                    )
    return errors, warnings


# 当前产品不支持的移动端和平板端视口模式。
MOBILE_VIEWPORT_PATTERNS = [
    re.compile(r'max-width\s*:\s*767px', re.IGNORECASE),
    re.compile(r'max-width\s*:\s*768px', re.IGNORECASE),
    re.compile(r'max-width\s*:\s*820px', re.IGNORECASE),
    re.compile(r'min-width\s*:\s*768px.*max-width\s*:\s*1024px', re.IGNORECASE),
    # ``@media`` 中出现通用移动端或平板端关键词同样视为引入支持。
    re.compile(r'@media[^{]*(?:mobile|tablet|ipad)', re.IGNORECASE),
]

# 这些桌面宽度可合法出现在 ``@media`` 中。
ALLOWED_DESKTOP_VIEWPORTS = {1400, 1440, 1512, 1920, 2560}


def _is_allowed_viewport(line: str) -> bool:
    """判断媒体查询是否明确使用受支持的桌面视口。"""
    for vw in ALLOWED_DESKTOP_VIEWPORTS:
        if f'{vw}px' in line:
            return True
    return False


def check_supported_viewports_only(
    css_files: list[Path],
    js_files: list[Path],
) -> tuple[list[str], list[str]]:
    """阻断 CSS/JavaScript 中新增的移动端或平板端视口支持。"""
    errors: list[str] = []
    warnings: list[str] = []
    all_files = css_files + js_files
    for path in all_files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            # 注释中的规则说明不代表实际启用视口行为。
            stripped = line.strip()
            if stripped.startswith('/*') or stripped.startswith('*') or stripped.startswith('//'):
                continue
            for pattern in MOBILE_VIEWPORT_PATTERNS:
                if pattern.search(line):
                    if _is_allowed_viewport(line):
                        continue
                    errors.append(
                        f'{path}:{lineno}: 禁止移动/平板视口支持 '
                        f'（rule: supported-viewports-only），'
                        f'仅支持桌面端视口。'
                    )
    return errors, warnings


def _css_has_only_comments_or_empty(text: str) -> bool:
    """判断 CSS 是否仅含注释或空白；纯 ``@import`` 入口文件不视为死文件。"""
    stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    stripped = stripped.strip()
    if not stripped:
        return True
    # ``@import`` 入口虽无规则体，仍承担样式组合职责。
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    has_import = any(l.startswith('@import') for l in lines)
    has_rules = '{' in stripped and '}' in stripped
    if has_import and not has_rules:
        return False  # 允许仅承载 import 的兼容包装器
    return not stripped or ('{' not in stripped and '}' not in stripped)


def _js_is_only_comments_or_empty(text: str) -> bool:
    """判断 JavaScript 是否只包含注释或空白。"""
    stripped = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    stripped = re.sub(r'/\*.*?\*/', '', stripped, flags=re.DOTALL)
    lines = [l for l in stripped.splitlines() if l.strip()]
    return len(lines) == 0


def check_no_dead_compat_shim(
    css_files: list[Path],
    js_files: list[Path],
) -> tuple[list[str], list[str]]:
    """阻断空静态文件以及仅靠 ``display:none`` 保留的旧选择器兼容垫片。"""
    errors: list[str] = []
    warnings: list[str] = []

    # 第一阶段识别没有任何有效规则或代码的静态文件。
    for path in css_files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if _css_has_only_comments_or_empty(text):
            errors.append(
                f'{path}: 死 CSS 文件（只有注释或空白，无有效 rule，rule: no-dead-compat-shim）。'
            )

    for path in js_files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        if _js_is_only_comments_or_empty(text):
            errors.append(
                f'{path}: 死 JS 文件（只有注释或空白，无有效代码，rule: no-dead-compat-shim）。'
            )

    legacy_like_pattern = re.compile(
        r'\.(?:old[-_]?|legacy[-_]?|deprecated[-_]?|compat[-_]?|v\d[-_]?)',
        re.IGNORECASE,
    )
    for path in css_files:
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if 'display' in line and 'none' in line:
                # 向前收集当前规则的选择器，确认隐藏逻辑是否只服务旧兼容命名。
                all_lines = text.splitlines()
                selector_lines = []
                for prev_idx in range(lineno - 2, max(lineno - 11, -1), -1):
                    if prev_idx < 0 or prev_idx >= len(all_lines):
                        continue
                    prev_line = all_lines[prev_idx]
                    selector_lines.append(prev_line)
                    if '{' in prev_line:
                        break

                selector_text = ' '.join(selector_lines)
                if legacy_like_pattern.search(selector_text):
                    errors.append(
                        f'{path}:{lineno}: display:none 用于疑似兼容垫片选择器 '
                        f'（rule: no-dead-compat-shim），'
                        f'请删除垫片或改为当前选择器。'
                    )

    return errors, warnings


def check_repo_slimming(repo_root: Path) -> tuple[list[str], list[str]]:
    """运行全部仓库瘦身回归检查并分别汇总错误与告警。"""
    errors: list[str] = []
    warnings: list[str] = []

    all_text_files: list[Path] = []
    for ext in ('*.css', '*.js', '*.html', '*.py', '*.md', '*.sh', '*.yaml', '*.json', '*.txt'):
        all_text_files.extend(repo_root.rglob(ext))
    exclude_dirs = {
        '.git',
        'node_modules',
        '__pycache__',
        '.pytest_cache',
        'tmp',
        '.mypy_cache',
        'dist',
        'venv',
        '.local',
    }
    excluded_files = {'repo_slimming_contract_check.py', 'test_repo_slimming_contract.py'}
    filtered_files = []
    for f in all_text_files:
        if any(ex in f.parts for ex in exclude_dirs):
            continue
        if f.name in excluded_files:
            continue
        filtered_files.append(f)
    e, w = check_no_historical_version_comments(filtered_files)
    errors.extend(e)
    warnings.extend(w)

    harness_dir = repo_root / 'harness'
    if harness_dir.exists():
        harness_files = list(harness_dir.rglob('*.md')) + list(harness_dir.rglob('*.yaml'))
        e, w = check_harness_current_state(harness_files)
        errors.extend(e)
        warnings.extend(w)

    static = repo_root / 'java/web/src/main/resources/static'
    if static.exists():
        css_files = list(static.rglob('*.css'))
        js_files = list(static.rglob('*.js'))
        e, w = check_supported_viewports_only(css_files, js_files)
        errors.extend(e)
        warnings.extend(w)

        e, w = check_no_dead_compat_shim(css_files, js_files)
        errors.extend(e)
        warnings.extend(w)

    return errors, warnings


def main() -> int:
    """执行仓库瘦身检查；任一阻断项存在时返回失败。"""

    errors, warnings = check_repo_slimming(Path.cwd())
    for item in warnings:
        print(f'[WARN] {item}')
    if errors:
        for item in errors:
            print(f'[BLOCK] {item}')
        return 1
    print(
        'repo slimming contract PASS'
        if not warnings
        else 'repo slimming contract PASS (with warnings)'
    )
    return 0
