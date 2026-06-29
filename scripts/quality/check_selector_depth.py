#!/usr/bin/env python3
"""CSS Selector Depth 阻断检查.

解析项目 CSS 文件中的所有选择器,计算嵌套深度,对超过阈值的
选择器标记 BLOCK/WARN 级别违规.

深度计算规则:
- 以空格,>,+,~ 等 CSS 组合符拆分选择器
- 拆分后非空部分的数量即为深度
- 例:".a .b .c" 深度 3;".a > .b + .c .d" 深度 4

阈值:
- depth > 3: BLOCK(阻断)
- depth == 3: WARN(警告,建议收敛)

用法:
    python3 scripts/quality/check_selector_depth.py

退出码:
    0 — 无 BLOCK 级违规(可能有 WARN)
    1 — 存在 BLOCK 级违规
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── 数据结构 ─────────────────────────────────────────────────────────────


@dataclass
class DepthViolation:
    """Describe one selector-depth violation emitted by the CSS quality gate.

    Attributes:
        severity: Stored severity value.
        file: Stored file value.
        selector: Stored selector value.
        depth: Stored depth value.
        line: Stored line value.
    """

    severity: str  # "BLOCK" | "WARN"
    file: str  # CSS 文件名
    selector: str  # 违规选择器
    depth: int  # 实际深度
    line: int | None = None


@dataclass
class DepthReport:
    """Aggregate selector-depth scan results for one quality gate invocation.

    Attributes:
        blocks: Stored blocks value.
        warnings: Stored warnings value.
        files_scanned: Stored files_scanned value.
        selectors_analyzed: Stored selectors_analyzed value.
        max_depth_seen: Stored max_depth_seen value.
        deepest_selector: Stored deepest_selector value.
        deepest_file: Stored deepest_file value.
    """

    blocks: list[DepthViolation] = field(default_factory=list)
    warnings: list[DepthViolation] = field(default_factory=list)
    files_scanned: int = 0
    selectors_analyzed: int = 0
    max_depth_seen: int = 0
    deepest_selector: str = ''
    deepest_file: str = ''


# ── 配置 ─────────────────────────────────────────────────────────────────

# 深度阈值:超过此值为 BLOCK
BLOCK_THRESHOLD = 3

# 建议阈值:超过此值为 WARN(含等于)
WARN_THRESHOLD = 2

# CSS 文件目录
# 脚本位于 scripts/quality/,CSS 位于 java/web/src/main/resources/static/css/
CSS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / 'java'
    / 'web'
    / 'src'
    / 'main'
    / 'resources'
    / 'static'
    / 'css'
)

# CSS 组合符正则:空格,>,+,~
COMBINATOR_RE = re.compile(r'\s+|(?<=[^\s])\s*(?:>|[+~])\s*|(?<=[^\s])(?:>|[+~])(?=[^\s])')


# ── CSS 解析工具 ─────────────────────────────────────────────────────────


def extract_css_rules(text: str) -> list[tuple[int, str, str]]:
    """提取 CSS 规则,返回 (行号, 选择器, 声明块) 列表.

    Args:
        text: Input value for text.

    Returns:
        Computed result.
    """
    rules: list[tuple[int, str, str]] = []
    stripped = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    lines = text.splitlines()

    char_to_line: dict[int, int] = {}
    pos = 0
    for i, line in enumerate(lines, 1):
        for _ in range(len(line) + 1):
            char_to_line[pos] = i
            pos += 1

    stack: list[tuple[str, int]] = []
    i = 0
    while i < len(stripped):
        if stripped[i] == '{':
            selector_start = i
            while selector_start > 0 and stripped[selector_start - 1] not in '{};':
                selector_start -= 1
            selector = stripped[selector_start:i].strip()
            stack.append((selector, selector_start))
        elif stripped[i] == '}' and stack:
            selector, start = stack.pop()
            body = stripped[start + 1 : i].strip()
            line_no = char_to_line.get(start, 0)
            if line_no > 0:
                rules.append((line_no, selector, body))
        i += 1

    return rules


def split_selectors(selector_str: str) -> list[str]:
    """按逗号拆分选择器,避开 :not() / :has() 等函数内的逗号.

    Args:
        selector_str: Input value for selector_str.

    Returns:
        Computed result.
    """
    depth = 0
    parts: list[str] = []
    current: list[str] = []
    for ch in selector_str:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return [p for p in parts if p and not p.startswith('@')]


def calculate_selector_depth(selector: str) -> int:
    """计算单个 CSS 选择器的嵌套深度.

    Args:
        selector: Input value for selector.

    Returns:
        Computed result.
    """
    selector = selector.strip()
    if not selector:
        return 0

    # 使用组合符拆分
    # 更精确的策略:先保护括号内内容,再拆分
    protected = selector
    # 将括号内内容临时替换,避免内部空格被误拆
    bracket_contents: list[str] = []

    def protect_brackets(m: re.Match) -> str:
        """Replace one bracketed selector fragment with a stable placeholder.

        Args:
            m: Input value for m.

        Returns:
            Computed result.
        """
        idx = len(bracket_contents)
        bracket_contents.append(m.group(0))
        return f'__BRACKET_{idx}__'

    protected = re.sub(r'\([^)]*\)', protect_brackets, protected)

    # 现在用组合符拆分
    # 组合符:空格(前后都不是括号占位符),>,+,~
    parts = re.split(r'\s*(?:>|[+~])\s*|\s+', protected)
    parts = [p.strip() for p in parts if p.strip()]

    return len(parts)


# ── 核心检查 ─────────────────────────────────────────────────────────────


def check_selector_depth(css_path: Path) -> DepthReport:
    """扫描单个 CSS 文件的选择器深度.

    Args:
        css_path: Input value for css_path.

    Returns:
        Computed result.
    """
    report = DepthReport()

    text = css_path.read_text(encoding='utf-8')
    rules = extract_css_rules(text)
    report.files_scanned = 1

    for lineno, selector_str, _body in rules:
        # 跳过 at-rules
        if selector_str.startswith('@'):
            continue

        selectors = split_selectors(selector_str)
        for raw_sel in selectors:
            sel = raw_sel.strip()
            if not sel:
                continue

            report.selectors_analyzed += 1
            depth = calculate_selector_depth(sel)

            if depth > report.max_depth_seen:
                report.max_depth_seen = depth
                report.deepest_selector = sel
                report.deepest_file = css_path.name

            if depth > BLOCK_THRESHOLD:
                report.blocks.append(
                    DepthViolation(
                        severity='BLOCK',
                        file=css_path.name,
                        selector=sel,
                        depth=depth,
                        line=lineno,
                    )
                )
            elif depth > WARN_THRESHOLD:
                report.warnings.append(
                    DepthViolation(
                        severity='WARN',
                        file=css_path.name,
                        selector=sel,
                        depth=depth,
                        line=lineno,
                    )
                )

    return report


def run_all_checks(css_dir: Path) -> DepthReport:
    """扫描目录下所有 CSS 文件.

    Args:
        css_dir: Input value for css_dir.

    Returns:
        Computed result.
    """
    total = DepthReport()

    css_files = sorted(css_dir.glob('*.css'))
    if not css_files:
        print(f'[ERROR] 未找到 CSS 文件: {css_dir}')
        return total

    for css_path in css_files:
        report = check_selector_depth(css_path)
        total.files_scanned += report.files_scanned
        total.selectors_analyzed += report.selectors_analyzed
        total.blocks.extend(report.blocks)
        total.warnings.extend(report.warnings)
        if report.max_depth_seen > total.max_depth_seen:
            total.max_depth_seen = report.max_depth_seen
            total.deepest_selector = report.deepest_selector
            total.deepest_file = report.deepest_file

    return total


# ── 报告输出 ─────────────────────────────────────────────────────────────


def print_report(report: DepthReport) -> None:  # noqa: PLR0912 - report sections mirror gate output.
    """打印人类可读的检查报告.

    Args:
        report: Input value for report.
    """
    print('=' * 72)
    print('CSS Selector Depth 检查报告')
    print('=' * 72)
    print(f'扫描文件数: {report.files_scanned}')
    print(f'分析选择器数: {report.selectors_analyzed}')
    print(f'最大深度: {report.max_depth_seen}')
    if report.deepest_selector:
        print(f'最深选择器: {report.deepest_selector} ({report.deepest_file})')
    print()

    if report.blocks:
        print(f'BLOCK 违规: {len(report.blocks)} 项')
        print('-' * 72)
        for v in report.blocks:
            line_info = f':{v.line}' if v.line else ''
            print(f'  [BLOCK] {v.file}{line_info} depth={v.depth}')
            print(f'          {v.selector}')
        print()

    if report.warnings:
        print(f'WARN 警告: {len(report.warnings)} 项')
        print('-' * 72)
        for v in report.warnings:
            line_info = f':{v.line}' if v.line else ''
            print(f'  [WARN] {v.file}{line_info} depth={v.depth}')
            print(f'         {v.selector}')
        print()

    if not report.blocks and not report.warnings:
        print(f'无违规.所有选择器深度均 <= {WARN_THRESHOLD}.')
        print()

    # 按文件汇总
    print('按文件汇总:')
    print('-' * 72)
    file_stats: dict[str, dict[str, int]] = {}
    for v in report.blocks + report.warnings:
        if v.file not in file_stats:
            file_stats[v.file] = {'BLOCK': 0, 'WARN': 0}
        file_stats[v.file][v.severity] += 1

    for fname in sorted(file_stats.keys()):
        s = file_stats[fname]
        parts = []
        if s['BLOCK']:
            parts.append(f'BLOCK={s["BLOCK"]}')
        if s['WARN']:
            parts.append(f'WARN={s["WARN"]}')
        print(f'  {fname}: {", ".join(parts)}')

    if not file_stats:
        print('  所有文件均无违规.')

    print()
    print('=' * 72)
    if report.blocks:
        print(f'结果: FAIL ({len(report.blocks)} 个 BLOCK 违规)')
    else:
        print('结果: PASS')
    print('=' * 72)


# ── 主入口 ───────────────────────────────────────────────────────────────


def main() -> int:
    """Run the selector-depth quality gate for repository CSS files.

    Returns:
        Computed result.
    """
    if not CSS_DIR.exists():
        print(f'[ERROR] CSS 目录不存在: {CSS_DIR}')
        return 2

    report = run_all_checks(CSS_DIR)
    print_report(report)

    if report.blocks:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
