#!/usr/bin/env python3
"""校验 feipi-session-browser 的 CSS ownership 规则。"""

import argparse
import re
import sys
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent / 'src' / 'session_browser' / 'web' / 'static'

# 必须只在 style.css 中定义的 shell selectors
SHELL_SELECTORS = {
    '.shell',
    '.app-shell',
    '.sidebar',
    '.topbar',
    '.content',
    '.footer',
    '.breadcrumb',
    '.topbar-breadcrumb',
    '.topbar-actions',
    '.main-panel',
    '.main',
    '.sd-shell',
    '.sd-content',
}

# 表示 shell override 的 layout properties（不只是 additive）
LAYOUT_PROPERTIES = {
    'display',
    'grid-template-columns',
    'grid-template-rows',
    'grid-template',
    'padding-top',
    'padding-right',
    'padding-bottom',
    'padding-left',
    'padding',
    'min-height',
    'max-height',
    'height',
    'min-width',
    'max-width',
    'width',
    'margin-top',
    'margin-right',
    'margin-bottom',
    'margin-left',
    'margin',
    'gap',
    'row-gap',
    'column-gap',
    'align-items',
    'justify-content',
    'align-content',
    'align-self',
    'position',
    'top',
    'left',
    'bottom',
    'flex-direction',
    'flex-wrap',
    'flex-basis',
    'flex-grow',
    'flex-shrink',
    'flex',
    'overflow-x',
    'overflow-y',
    'overflow',
    'z-index',
}

# Layer 3 允许 additive（仅 color/font/background）的 selectors
SHELL_SELECTORS_ADDITIVE = {
    '.topbar-breadcrumb',
    '.sidebar',  # compat-era: background, border-right (additive)
    '.main',  # compat-era: min-width (additive)
    '.sd-shell',  # compat-era: background var; session-detail: CSS variables only
}

# 不应出现在 style.css 中的 page-specific selectors
PAGE_SPECIFIC_SELECTORS = [
    '.chart-card',
    '.chart-group',
    '.chart-group__stack',
    '.segment',
    '.legend-row',
    '.legend-item',
    '.legend-dot',
    '.page-head',
    '.scope-switch',
    '.sessions-page',
    '.token-cell',
    '.token-total',
    '.tokenbar-seg',
    '.sessions-filter-card',
    '.sessions-control-row',
    '.sd-hero',
    '.sd-tabs',
    '.trace-table',
    '.trace-round',
    '.hero-metrics',
    '.project-cell',
    '.project-name',
    '.project-tooltip',
    '.glossary-table',
    '.term-cell',
    '.formula-cell',
    '.sample-cell',
    '.state-panel',
    '.error-icon',
    '.error-title',
    '.error-description',
    '.metric-grid--glossary',
    '.legend-card',
    '.note-strip',
    '.ui-stat-pill',
    '.ui-search',
]

# 禁止的 filename patterns
FORBIDDEN_PATTERNS = [
    re.compile(r'-v\d+\.css$'),  # versioned CSS like dashboard-v16.css
    re.compile(r'-patch\.css$'),  # session-patch.css
    re.compile(r'-fix\.css$'),  # something-fix.css
    re.compile(r'-overlay\.css$'),  # something-overlay.css
    re.compile(r'-reference\.css$'),  # something-reference.css
]

# 已知合法的 Layer 3/4 文件（允许存在）
KNOWN_CSS = {
    'css/dashboard.css',
    'css/sessions-list.css',
    'css/session-detail.css',
    'css/projects.css',
    'css/glossary.css',
    'css/states.css',
    'css/ui-primitives.css',
    'css/shell.css',
}

# ── 辅助函数 ────────────────────────────────────────────────────────────────


# 提取selectors。
def extract_selectors(css_path: Path) -> set[str]:
    """参数：
        css_path: CSS 文件以检查。

    返回：
        Set of class 或 id selectors defined by 文件；读取 错误 produce 空 set。
    """
    selectors = set()
    try:
        text = css_path.read_text()
    except Exception:
        return selectors

    # 移除 CSS comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # 匹配 `{` 之前的 selectors，并处理逗号分组
    for match in re.finditer(r'([^{}]+?)\s*\{', text):
        group = match.group(1).strip()
        # 跳过 @-rules
        if group.startswith('@') or not group:
            continue
        # 拆分逗号分隔的 selector
        for raw_sel in group.split(','):
            sel = raw_sel.strip()
            if not sel or sel.startswith('@'):
                continue
            # 提取 base selector（第一个 class/element 名称）
            parts = sel.split()
            if parts:
                full = parts[0].split(':')[0].split('[')[0]
                if full.startswith(('.', '#')):
                    selectors.add(full)
    return selectors


# 判断是否存在shell selector。
def has_shell_selector(css_path: Path) -> list[tuple[str, str]]:
    """参数：
        css_path: CSS 文件以检查。

    返回：
        列出of selector 和 行-数字 details that violate shell ownership rules。
    """
    violations = []
    try:
        text = css_path.read_text()
    except Exception:
        return violations

    # 移除 comments 便于分析
    clean = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    # 查找所有 rule blocks
    pos = 0
    while True:
        m = re.search(r'([^{}]+?)\s*\{([^{}]*)\}', clean[pos:])
        if not m:
            break

        selector_text = m.group(1).strip()
        rule_body = m.group(2).strip()
        abs_pos = pos + m.start()

        # 计算当前规则所在行号
        line_num = clean[:abs_pos].count('\n') + 1

        # 拆分逗号分隔的 selector
        selectors = [s.strip() for s in selector_text.split(',') if s.strip()]

        for sel_full in selectors:
            # 目标 shell selector 必须只匹配 shell class 本身，
            # 可以带 `.no-inspector` 这类 modifier，
            # 但不能是 `.sd-shell .child` 这类 descendant chain。
            # 例如 `.topbar` → target（单段）
            # 例如 `.shell.no-inspector` → target（同一 class 上的 modifier）
            # 例如 `.sd-shell .child` → 非 target（多段 descendant）
            parts = sel_full.split()
            if len(parts) > 1:
                continue  # descendant selector，跳过
            if not parts:
                continue
            first_part = parts[0].split(':')[0].split('[')[0]

            if first_part not in SHELL_SELECTORS:
                continue

            # 检查是否为允许的 additive selector
            if first_part in SHELL_SELECTORS_ADDITIVE:
                # 检查是否定义 layout properties
                has_layout = any(
                    re.search(rf'\b{re.escape(prop)}\s*:', rule_body) for prop in LAYOUT_PROPERTIES
                )
                if not has_layout:
                    continue

            # 这是违规 selector
            preview = rule_body[:80].replace('\n', ' ').strip()
            violations.append((first_part, f'line {line_num}: {sel_full} {{ {preview} ... }}'))

        pos = abs_pos + m.end() - m.start()

    return violations


# 检查bloat。
def check_bloat(css_path: Path) -> list[tuple[str, str]]:
    """参数：
        css_path: Global style.css 路径以检查。

    返回：
        列出of selector 和 reason tuples用于bloat violations。
    """
    violations = []
    try:
        text = css_path.read_text()
    except Exception:
        return violations

    for sel in PAGE_SPECIFIC_SELECTORS:
        # 使用 word boundary 避免误报
        pattern = re.compile(
            r'(?:^|[\s,;{}])' + re.escape(sel) + r'(?:\.[\w-]+|::?\w+|\[.*?\])?\s*\{', re.MULTILINE
        )
        matches = pattern.findall(text)
        if matches:
            violations.append((sel, f'found {len(matches)} occurrence(s)'))
    return violations


# 检查forbidden names。
def check_forbidden_names(css_dir: Path) -> list[tuple[str, str]]:
    """参数：
        css_dir: Static CSS 目录到scan。

    返回：
        列出of relative 文件路径s 和 reasons用于forbidden filenames。
    """
    violations = []
    for f in sorted(css_dir.rglob('*.css')):
        rel = str(f.relative_to(css_dir))
        if f.name in ('style.css', 'ui-primitives.css'):
            continue
        if str(f.relative_to(css_dir)) in KNOWN_CSS:
            continue
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(f.name):
                violations.append((rel, f'forbidden filename pattern: {pat.pattern}'))
                break
    return violations


# 检查duplicates。
def check_duplicates(css_dir: Path, verbose: bool = False) -> list[tuple[str, str]]:  # noqa: PLR0912, PLR0915 - duplicate scan keeps rule context inline.
    """参数：
        css_dir: Static CSS 目录到scan。
        verbose: 当 true, 打印 duplicate selector 诊断信息 当 scanning。

    返回：
        列出of selector 和 文件-列表 details用于disallowed duplicates。
    """
    violations = []
    selector_map: dict[str, list[str]] = {}

    css_files = sorted(css_dir.rglob('*.css'))
    for f in css_files:
        rel = str(f.relative_to(css_dir))
        if f.name == 'style.css':
            continue  # Layer 1 是权威定义
        if rel == 'css/shell.css':
            continue  # Layer 2 是 shell 权威定义
        sels = extract_selectors(f)
        for sel in sels:
            if sel not in selector_map:
                selector_map[sel] = []
            selector_map[sel].append(rel)

    for sel, files in sorted(selector_map.items()):
        if len(files) > 1:
            # 检查是否为 shell selector（应只在 style.css 中定义）
            base = sel.split(':')[0].split('[')[0]
            if base in SHELL_SELECTORS:
                # 例外：仅用于 CSS variable scoping 的 shell selector
                # 例如 `.sd-shell { --sd-bg: ... }` 可出现在多个文件
                # 因为它们不定义 layout，只定义 token namespace。
                all_var_only = True
                for f in files:
                    full_path = css_dir / f
                    try:
                        text = re.sub(r'/\*.*?\*/', '', full_path.read_text(), flags=re.DOTALL)
                    except Exception:
                        all_var_only = False
                        break
                    # 查找所有规则，并检查 `sel` 是否作为 target selector 出现。
                    rule_pattern = re.compile(r'([^{}]+?)\s*\{([^}]*)\}')
                    found_target = False
                    for m in rule_pattern.finditer(text):
                        sel_text = m.group(1).strip()
                        body = m.group(2)
                        # 检查每个逗号分隔的 sub-selector
                        for raw_sub in sel_text.split(','):
                            sub = raw_sub.strip()
                            parts = sub.split()
                            if not parts:
                                continue
                            # 只匹配精确 target selector，不匹配 descendant
                            if len(parts) > 1:
                                continue
                            first = parts[0].split(':')[0].split('[')[0]
                            if first == sel:
                                # 这是页面外壳选择器对应的目标规则。
                                # 去除 CSS 变量定义（--name: value），
                                # 去除变量使用（var(--name) → VAR），以及
                                # 属性值仅为变量占位符时不计入冗余样式。
                                stripped = re.sub(r'--[\w-]+\s*:[^;]*;', '', body)
                                stripped = re.sub(r'var\([^)]*\)', 'VAR', stripped)
                                stripped = re.sub(r'[\w-]+\s*:\s*VAR\s*;?', '', stripped)
                                has_non_var = bool(stripped.strip())
                                if has_non_var:
                                    all_var_only = False
                                else:
                                    found_target = True
                                break
                        if not all_var_only:
                            break
                    if not found_target:
                        all_var_only = False
                        break
                if all_var_only:
                    continue  # 仅 CSS variable scoping，允许
                violations.append(
                    (
                        sel,
                        f'defined in {len(files)} files: {", ".join(files)} '
                        f'(shell selectors must be in style.css only)',
                    )
                )
            elif verbose:
                # 非 shell duplicate 仅作为信息，不算违规
                if verbose:
                    violations.append(
                        (sel, f'[INFO] defined in {len(files)} files: {", ".join(files)}')
                    )
    return violations


# ── 主流程 ───────────────────────────────────────────────────────────────────


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description='Validate CSS ownership rules')
    parser.add_argument('--verbose', action='store_true', help='Show info-level duplicates')
    args = parser.parse_args()

    violations = []

    # 1. 检查 Layer 3/4 文件中的 shell selector 违规
    layer34_files = [
        ROOT / 'css/dashboard.css',
        ROOT / 'css/sessions-list.css',
        ROOT / 'css/session-detail.css',
        ROOT / 'css/projects.css',
        ROOT / 'css/glossary.css',
        ROOT / 'css/states.css',
    ]
    for f in layer34_files:
        if not f.exists():
            continue
        rel = str(f.relative_to(ROOT))
        v = has_shell_selector(f)
        for sel, ctx in v:
            violations.append(('shell_selector_violation', rel, f'{sel} — {ctx}'))

    # 2. 检查禁止的文件名
    for name, ctx in check_forbidden_names(ROOT):
        violations.append(('forbidden_filename', name, ctx))

    # 3. 检查 style.css bloat
    style_css = ROOT / 'style.css'
    if style_css.exists():
        for sel, ctx in check_bloat(style_css):
            violations.append(('style_bloat', 'style.css', f'{sel} — {ctx}'))

    # 4. 检查 duplicate selectors
    for sel, ctx in check_duplicates(ROOT, verbose=args.verbose):
        if '[INFO]' in ctx:
            continue  # 仅信息项，非 verbose 模式跳过
        violations.append(('duplicate_selector', 'multiple', f'{sel} — {ctx}'))

    # ── 报告 ─────────────────────────────────────────────────────────
    if violations:
        print(f'\n{"=" * 60}')
        print('CSS Ownership Validation — FAIL')
        print(f'{"=" * 60}')

        by_type: dict[str, list] = {}
        for vtype, file, detail in violations:
            by_type.setdefault(vtype, []).append((file, detail))

        for vtype, items in sorted(by_type.items()):
            print(f'\n--- {vtype} ({len(items)} issue(s)) ---')
            for file, detail in items:
                print(f'  [{file}] {detail}')

        print(f'\n{"=" * 60}')
        print(f'Total: {len(violations)} violation(s)')
        print(f'{"=" * 60}\n')
        return 1
    print(f'\n{"=" * 60}')
    print('CSS Ownership Validation — PASS')
    print(f'{"=" * 60}')
    print('No violations found.\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
