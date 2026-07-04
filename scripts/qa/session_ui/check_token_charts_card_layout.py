#!/usr/bin/env python3
"""提供 检查 token charts card 布局 脚本能力。"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print('ERROR: beautifulsoup4 is required. Install with: pip install beautifulsoup4')
    sys.exit(2)

# ---------------------------------------------------------------------------
# 路径。
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE = (
    REPO_ROOT / 'reports' / 'session-detail-hifi-layout-quality' / 'baseline' / 'current.html'
)
DEFAULT_URL = 'http://localhost:18999/session/93ecbcf2'


# 维护获取 HTML。
def fetch_html(url: str, timeout: float = 3.0) -> str | None:
    """参数：
        url: 待请求的 URL。
        timeout: 超时时间，单位为秒。

    返回：
        fetch HTML 字符串。
    """
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'token-metrics-check/2.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


# 读取HTML。
def read_html(path: Path) -> str | None:
    """参数：
        path: Local HTML 文件路径 supplied on CLI。

    返回：
        HTML text 当 文件 exists；None 之后 printing 文件 错误。
    """
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except (OSError, FileNotFoundError):
        return None


# 加载源码。
def load_source(url: str | None, html_path: Path | None) -> tuple[str | None, str]:
    """参数：
        url: 待请求的 URL。
        html_path: 可选local fixture 路径 selected by CLI。

    返回：
        由HTML text 和 source label; exits带状态 2 当 no 读取able source组成的 tuple。 is 可用。
    """
    if url:
        content = fetch_html(url)
        if content:
            return content, f'server ({url})'
    if html_path and html_path.is_file():
        content = read_html(html_path)
        if content:
            return content, f'file ({html_path})'
    return None, None


# 检查token 总量 kpis。
def check_token_total_in_kpis(soup: BeautifulSoup) -> tuple[str, list[str]]:  # noqa: PLR2004 - QA thresholds encode contract counts.
    """参数：
        soup: 已解析的session-detail HTML document。

    返回：
        结果 tuple。
    """
    notes: list[str] = []
    pass_count = 0

    # 检查用于 KPIs section。
    kpis = soup.select_one('.kpis')
    if kpis:
        notes.append('hero KPIs section found')
        pass_count += 1

        kpi_labels = kpis.select('.kpi .l')
        token_kpi = None
        for label in kpi_labels:
            text = label.get_text(strip=True).lower()
            if 'token' in text:
                token_kpi = label
                break

        if token_kpi:
            # 检查the corresponding 值。
            value_el = token_kpi.find_previous_sibling(class_='v')
            if value_el:
                val_text = value_el.get_text(strip=True)
                notes.append(
                    f"token KPI value: '{val_text}' (label: '{token_kpi.get_text(strip=True)}')"
                )
                pass_count += 1
            else:
                notes.append('token KPI label found but no value sibling')
        else:
            notes.append("No KPI label contains 'token'")

        secondary = soup.select_one('.hero-secondary-metrics')
        if secondary:
            sec_text = secondary.get_text()
            if '总 Token' in sec_text or 'total token' in sec_text.lower():
                notes.append('total tokens present in secondary metrics strip')
                pass_count += 1
    else:
        notes.append('hero KPIs section NOT found')

    if pass_count >= 2:
        return 'PASS', notes
    if pass_count >= 1:
        return 'WARN', notes
    notes.append('FAIL: no token total found in hero KPIs')
    return 'FAIL', notes


# 检查highest token round issues。
def check_highest_token_round_in_issues(soup: BeautifulSoup) -> tuple[str, list[str]]:  # noqa: PLR2004 - QA thresholds encode contract counts.
    """参数：
        soup: 已解析的session-detail HTML document。

    返回：
        结果 tuple。
    """
    notes: list[str] = []
    pass_count = 0

    # 检查用于 issue summary section。
    issue_section = soup.select_one('[data-issue-summary], .issue-summary')
    if issue_section:
        notes.append('issue summary section found')
        pass_count += 1
    else:
        notes.append('issue summary section NOT found')
        return 'WARN', notes  # Not a hard failure

    cost_card = issue_section.select_one('.issue-card--cost')
    if cost_card:
        title = cost_card.select_one('.issue-card__title')
        sub = cost_card.select_one('.issue-card__sub')
        if title:
            title_text = title.get_text(strip=True)
            notes.append(f"highest token round card title: '{title_text}'")
            pass_count += 1

            # 检查如果 it mentions "tokens"。
            if 'token' in title_text.lower():
                notes.append("card title contains 'tokens' keyword")
                pass_count += 1

        if sub:
            notes.append(f"card subtitle: '{sub.get_text(strip=True)}'")
    else:
        notes.append('No highest-token-round cost card found (may be OK if no data or round < 2)')

    jump_buttons = issue_section.select('[data-action="jump-round"][data-round]')
    if jump_buttons:
        notes.append(f'jump-round buttons in issue summary: {len(jump_buttons)}')

    if pass_count >= 2:
        return 'PASS', notes
    if pass_count >= 1:
        return 'WARN', notes
    return 'WARN', notes


# 检查per round token 数据。
def check_per_round_token_data(soup: BeautifulSoup) -> tuple[str, list[str]]:  # noqa: PLR2004 - QA thresholds encode contract counts.
    """参数：
        soup: 已解析的session-detail HTML document。

    返回：
        状态 label 和 diagnostic messages用于per-round token visibility。
    """
    notes: list[str] = []
    pass_count = 0

    trace_rows = soup.select('.trace-row')
    if not trace_rows:
        notes.append('No trace rows found')
        return 'FAIL', notes

    notes.append(f'trace rows found (count={len(trace_rows)})')
    pass_count += 1

    # 检查用于 .mixval in trace 行。
    rows_with_mixval = soup.select('.trace-row .mixval')
    if rows_with_mixval:
        notes.append(f'.mixval elements found in trace rows (count={len(rows_with_mixval)})')
        pass_count += 1

        # 验证值 are non-空。
        sample_values = [el.get_text(strip=True) for el in rows_with_mixval[:3]]
        notes.append(f'sample mixval values: {sample_values}')
    else:
        notes.append('No .mixval elements found in trace rows')

    # 检查用于 data-round-tokens attribute on trace 行。
    rows_with_token_data = [r for r in trace_rows if r.get('data-round-tokens')]
    if rows_with_token_data:
        notes.append(f'trace rows with data-round-tokens: {len(rows_with_token_data)}')
        pass_count += 1

        sample = [r['data-round-tokens'] for r in rows_with_token_data[:3]]
        notes.append(f'sample data-round-tokens values: {sample}')
    else:
        notes.append('No data-round-tokens attributes on trace rows')

    # 检查用于 mixbar (token composition bar)。
    mixbars = soup.select('.trace-row .mixbar')
    if mixbars:
        notes.append(f'mixbar elements found (count={len(mixbars)})')
        pass_count += 1
    else:
        notes.append('No mixbar elements found')

    if pass_count >= 3:
        return 'PASS', notes
    if pass_count >= 2:
        return 'WARN', notes
    return 'FAIL', notes


# 检查 token charts card 已移除。
def check_token_charts_card_removed(soup: BeautifulSoup) -> tuple[str, list[str]]:
    """参数：
        soup: 已解析的session-detail HTML document。

    返回：
        状态 label 和 diagnostic messages用于removed-card enforcement。
    """
    notes: list[str] = []

    chart_cards = soup.select('.token-charts-card')
    chart_bodies = soup.select('div.token-charts-card__body')

    if chart_cards:
        notes.append(f'VIOLATION: .token-charts-card still present (count={len(chart_cards)})')
        return 'FAIL', notes
    if chart_bodies:
        notes.append(
            f'VIOLATION: .token-charts-card__body still present (count={len(chart_bodies)})'
        )
        return 'FAIL', notes
    notes.append('OK: token-charts-card fully removed (Phase 1 target state)')
    return 'PASS', notes


# ---------------------------------------------------------------------------
# 主流程。
# ---------------------------------------------------------------------------

CHECKS = [
    ('Token total in hero KPIs', check_token_total_in_kpis),
    ('Highest token round in issues', check_highest_token_round_in_issues),
    ('Per-round token data in traces', check_per_round_token_data),
    ('token-charts-card removed', check_token_charts_card_removed),
]


# 运行检查。
def run_checks(html: str, source: str) -> dict:
    """参数：
        html: 待检查的 HTML 文本。
        source: 输入来源标识。

    返回：
        映射从check name到状态 和 diagnostic messages。
    """
    soup = BeautifulSoup(html, 'html.parser')
    results = {}
    for name, fn in CHECKS:
        status, notes = fn(soup)
        results[name] = {'status': status, 'notes': notes}
    return results


# 打印报告。
def print_report(results: dict, source: str) -> bool:
    """参数：
        results: results 参数。
        source: 输入来源标识。

    返回：
        当every 检查 passed; 当 any 检查 失败.时返回 true。
    """
    print(f'\n{"=" * 60}')
    print('  Token Metrics Placement Check (Phase 1)')
    print(f'  Source: {source}')
    print(f'{"=" * 60}\n')

    any_fail = False
    for name, data in results.items():
        status = data['status']
        if status == 'FAIL':
            any_fail = True
        icon = {'PASS': '[PASS]', 'WARN': '[WARN]', 'FAIL': '[FAIL]'}.get(status, '[??]')
        print(f'  {icon}  {name}')
        for note in data['notes']:
            print(f'        {note}')
        print()

    # 结果汇总。
    counts = {'PASS': 0, 'WARN': 0, 'FAIL': 0}
    for data in results.values():
        s = data['status']
        if s in counts:
            counts[s] += 1

    print(f'{"=" * 60}')
    print(f'  Checked: {counts["PASS"]} PASS, {counts["WARN"]} WARN, {counts["FAIL"]} FAIL')
    print(f'  Verdict: {"PASS" if not any_fail else "FAIL"}')
    print(f'{"=" * 60}\n')

    return not any_fail


# 解析命令行参数并运行脚本入口。
def main() -> None:
    parser = argparse.ArgumentParser(description='Token metrics placement check for Phase 1')
    parser.add_argument(
        '--url', default=DEFAULT_URL, help='URL to fetch page from (default: %(default)s)'
    )
    parser.add_argument(
        '--html', default=str(DEFAULT_BASELINE), help='Path to baseline HTML file (fallback)'
    )
    args = parser.parse_args()

    html_path = Path(args.html) if args.html else None
    content, source = load_source(args.url, html_path)

    if content is None:
        print(f'ERROR: Could not load HTML from {args.url} or {html_path}')
        print('Start the local server or provide a valid HTML file path.')
        sys.exit(2)

    print(f'Loaded HTML from: {source}')
    print(f'  Size: {len(content):,} bytes, {content.count(chr(10)):,} lines')

    results = run_checks(content, source)
    success = print_report(results, source)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
