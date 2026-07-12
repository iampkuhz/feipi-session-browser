#!/usr/bin/env python3
"""No-ID-Selector 阻断检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

# ── 数据结构 ─────────────────────────────────────────────────────────────


@dataclass
class IdViolation:
    """表示一条 IdViolation 检查发现。

    属性：
        severity: severity 参数。
        file: 待检查的文件。
        selector: 待检查的 CSS selector。
        id_name: id name 参数。
        line: 待检查的源码行。
    """

    severity: str  # 取值为 BLOCK 或 WARN
    file: str  # CSS 文件名
    selector: str  # 违规选择器(含可能的组合器,如 "#foo.is-hidden")
    id_name: str  # 提取的 ID 名称(如 "glossary-empty")
    line: int | None = None


@dataclass
class IdReport:
    """汇总 IdReport 的检查结果。

    属性：
        blocks: blocks 参数。
        warnings: 警告列表。
        files_scanned: files scanned 参数。
        selectors_analyzed: selectors analyzed 参数。
        id_selectors_found: id selectors found 参数。
    """

    blocks: list[IdViolation] = field(default_factory=list)
    warnings: list[IdViolation] = field(default_factory=list)
    files_scanned: int = 0
    selectors_analyzed: int = 0
    id_selectors_found: int = 0


# ── 配置 ─────────────────────────────────────────────────────────────────

# 存量 ID 选择器白名单(仅 ID 名称部分)
STOCK_IDS: set[str] = {
    'glossary-empty',
    'agents-empty',
    'projects-empty',
}

# CSS 文件目录
CSS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / 'src'
    / 'session_browser'
    / 'web'
    / 'static'
    / 'css'
)

# ID 选择器匹配正则:匹配 # 后跟合法 CSS 标识符
# 排除纯十六进制颜色值(如 #fff, #d9e2ef)
ID_SELECTOR_RE = re.compile(r'(?:^|[\s,>+~\[(])#([a-zA-Z_][\w-]*)')

# 触发模式：当变更文件匹配时运行此检查
TRIGGER_PATTERNS = [
    'java/web/src/main/resources/static/**/*.js',
    'java/web/src/main/resources/static/**/*.css',
]


# 提取 CSS rule 及其源码位置，不修改原始文本。
def extract_css_rules(text: str) -> list[tuple[int, str, str]]:
    """提取 CSS rule 及其源码位置，不修改原始文本。"""
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


# 维护拆分 selectors。
def split_selectors(selector_str: str) -> list[str]:
    """维护拆分 selectors。"""
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


# 提取选择器中声明的 ID 名称。
def extract_id_names(selector: str) -> list[str]:
    """提取选择器中声明的 ID 名称。"""
    ids: list[str] = []
    for match in ID_SELECTOR_RE.finditer(selector):
        id_name = match.group(1)
        # 排除纯十六进制颜色(仅含 0-9, a-f, A-F,长度 3-8)
        if re.fullmatch(r'[0-9a-fA-F]{3,8}', id_name):
            continue
        ids.append(id_name)
    return ids


# 检查禁止使用的 ID 选择器。
def check_id_selectors(css_path: Path) -> IdReport:
    """检查禁止使用的 ID 选择器。"""
    report = IdReport()

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
            id_names = extract_id_names(sel)

            for id_name in id_names:
                report.id_selectors_found += 1

                if id_name in STOCK_IDS:
                    report.warnings.append(
                        IdViolation(
                            severity='WARN',
                            file=css_path.name,
                            selector=sel,
                            id_name=id_name,
                            line=lineno,
                        )
                    )
                else:
                    report.blocks.append(
                        IdViolation(
                            severity='BLOCK',
                            file=css_path.name,
                            selector=sel,
                            id_name=id_name,
                            line=lineno,
                        )
                    )

    return report


# 运行全部 检查。
def run_all_checks(css_dir: Path) -> IdReport:
    """运行全部 检查。"""
    total = IdReport()

    css_files = sorted(css_dir.glob('*.css'))
    if not css_files:
        print(f'[ERROR] 未找到 CSS 文件: {css_dir}')
        return total

    for css_path in css_files:
        report = check_id_selectors(css_path)
        total.files_scanned += report.files_scanned
        total.selectors_analyzed += report.selectors_analyzed
        total.id_selectors_found += report.id_selectors_found
        total.blocks.extend(report.blocks)
        total.warnings.extend(report.warnings)

    return total


# ── 报告输出 ─────────────────────────────────────────────────────────────


# 打印报告。
def print_report(report: IdReport) -> None:  # noqa: PLR0912 - report sections map to gate output.
    """参数：
    report: report 参数。
    """
    print('=' * 72)
    print('No-ID-Selector 检查报告')
    print('=' * 72)
    print(f'扫描文件数: {report.files_scanned}')
    print(f'分析选择器数: {report.selectors_analyzed}')
    print(f'发现 ID 选择器数: {report.id_selectors_found}')
    print(f'存量白名单: {", ".join(sorted(STOCK_IDS))}')
    print()

    if report.blocks:
        print(f'BLOCK 违规(新增 ID 选择器,必须移除): {len(report.blocks)} 项')
        print('-' * 72)
        for v in report.blocks:
            line_info = f':{v.line}' if v.line else ''
            print(f'  [BLOCK] {v.file}{line_info} id=#{v.id_name}')
            print(f'          {v.selector}')
        print()

    if report.warnings:
        print(f'WARN 警告(存量 ID 选择器,建议迁移到 class): {len(report.warnings)} 项')
        print('-' * 72)
        for v in report.warnings:
            line_info = f':{v.line}' if v.line else ''
            print(f'  [WARN] {v.file}{line_info} id=#{v.id_name}')
            print(f'         {v.selector}')
        print()

    if not report.blocks and not report.warnings:
        print('无 ID 选择器.')
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
        print('  所有文件均无 ID 选择器.')

    print()
    print('=' * 72)
    if report.blocks:
        print(f'结果: FAIL ({len(report.blocks)} 个 BLOCK 违规)')
    else:
        print('结果: PASS')
    print('=' * 72)


# ── 主入口 ───────────────────────────────────────────────────────────────


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """解析命令行参数并运行脚本入口。"""
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

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
