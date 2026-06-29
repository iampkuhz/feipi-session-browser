#!/usr/bin/env python3
"""raw-innerHTML 阻断 gate.

扫描仓库中所有 JS 文件的 innerHTML 赋值,执行以下策略:
- 存量 innerHTML 使用标记为 WARN(技术债务)
- 新增 innerHTML 使用标记为 BLOCK(阻断)

用法:
    # 全量扫描(生成 baseline 或仅报告)
    python3 scripts/quality/check_raw_innerhtml.py

    # 增量检查(对比 baseline,发现新增则 BLOCK)
    python3 scripts/quality/check_raw_innerhtml.py --check

    # 更新 baseline(在已知安全的新增后手动运行)
    python3 scripts/quality/check_raw_innerhtml.py --update-baseline

退出码:
    0 — 无新增 innerHTML 使用(全量扫描始终返回 0)
    1 — 发现新增 innerHTML 使用(--check 模式)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_PATH = REPO_ROOT / 'scripts' / 'quality' / 'innerhtml_baseline.json'

# 匹配 innerHTML 赋值:element.innerHTML = ...
# 不匹配读取:x = element.innerHTML
INNERHTML_ASSIGN_RE = re.compile(r'\.innerHTML\s*=')

# 匹配注释行(// ... 或 /* ... */)中的 innerHTML,排除纯注释
COMMENT_LINE_RE = re.compile(r'^\s*(?://|/\*|\*)')

# 排除清空操作(.innerHTML = '' 或 .innerHTML = ""),视为安全
CLEAR_ASSIGN_RE = re.compile(r"\.innerHTML\s*=\s*['\"]\s*['\"]")


def find_js_files(root: Path) -> list[Path]:
    """递归查找所有 .js 文件.

    Args:
        root: Input value for root.

    Returns:
        Computed result.
    """
    js_dirs = [
        root / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'js',
        root / 'tests',
    ]
    results: list[Path] = []
    for d in js_dirs:
        if d.is_dir():
            results.extend(sorted(d.rglob('*.js')))
    # 也包括 scripts/ 下的 JS(如有)
    scripts_dir = root / 'scripts'
    if scripts_dir.is_dir():
        results.extend(sorted(scripts_dir.rglob('*.js')))
    return results


def scan_innerhtml_assignments(js_files: list[Path]) -> list[dict]:
    """扫描 JS 文件,返回所有 innerHTML 赋值位置.

    Args:
        js_files: Input value for js_files.

    Returns:
        Computed result.
    """
    findings: list[dict] = []
    for js_file in js_files:
        try:
            text = js_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        rel_path = str(js_file.relative_to(REPO_ROOT))
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # 跳过注释行
            if COMMENT_LINE_RE.match(stripped):
                continue
            if INNERHTML_ASSIGN_RE.search(line):
                is_clear = bool(CLEAR_ASSIGN_RE.search(line))
                findings.append(
                    {
                        'file': rel_path,
                        'line': line_no,
                        'isClear': is_clear,
                        'snippet': stripped[:120],
                    }
                )
    return findings


def load_baseline() -> set[str]:
    """加载 baseline,返回已知 innerHTML 位置的集合.

    Returns:
        Computed result.
    """
    if not BASELINE_PATH.exists():
        return set()
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
        return {entry['file'] + ':' + str(entry['line']) for entry in data.get('entries', [])}
    except (json.JSONDecodeError, KeyError, ValueError):
        return set()


def save_baseline(findings: list[dict]) -> None:
    """将当前扫描结果保存为 baseline.

    Args:
        findings: Input value for findings.
    """
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(
            {'version': 1, 'entries': findings, 'count': len(findings)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )


def run_check(args: argparse.Namespace) -> int:
    """Run the raw-innerHTML check or report mode.

    Args:
        args: Input value for args.

    Returns:
        Computed result.
    """
    js_files = find_js_files(REPO_ROOT)
    if not js_files:
        print('未找到 JS 文件.')
        return 0

    findings = scan_innerhtml_assignments(js_files)
    baseline = load_baseline()
    known_count = 0
    new_items: list[dict] = []

    for f in findings:
        key = f['file'] + ':' + str(f['line'])
        if key in baseline:
            known_count += 1
        else:
            new_items.append(f)

    total = len(findings)
    clear_count = sum(1 for f in findings if f['isClear'])

    print('=== raw-innerHTML 阻断 gate ===')
    print(f'扫描文件数:{len(js_files)}')
    print(f'innerHTML 赋值总数:{total}(含清空操作 {clear_count} 处)')
    print(f'存量 WARN:{known_count} 处(技术债务)')
    print(f'新增 BLOCK:{len(new_items)} 处')
    print()

    if known_count > 0:
        print('--- 存量 innerHTML(WARN)---')
        for f in findings:
            key = f['file'] + ':' + str(f['line'])
            tag = '[WARN]' if key in baseline else '[NEW!!]'
            clear_tag = ' (清空)' if f['isClear'] else ''
            print(f'  {tag} {f["file"]}:{f["line"]}{clear_tag} | {f["snippet"]}')
        print()

    if new_items:
        print('!!! 新增 innerHTML 使用(BLOCK) !!!')
        for f in new_items:
            print(f'  [BLOCK] {f["file"]}:{f["line"]} | {f["snippet"]}')
        print()
        print('结论:FAIL — 检测到新增 innerHTML 赋值,违反 raw-innerHTML 阻断策略.')
        print('如需豁免,请先修复为 textContent 或 escapeHtml(),或经审阅后运行 --update-baseline.')
        return 1

    if args.check:
        print('结论:PASS — 无新增 innerHTML 赋值.')
        return 0

    # 全量扫描模式
    print('结论:PASS(全量扫描)— 存量技术债务已记录.')
    if not baseline:
        print('提示:首次运行,建议执行 --update-baseline 建立 baseline.')
        print(f'  baseline 路径:{BASELINE_PATH}')
    return 0


def run_update_baseline(args: argparse.Namespace) -> int:
    """Rewrite the raw-innerHTML baseline from the current scan.

    Args:
        args: Input value for args.

    Returns:
        Computed result.
    """
    js_files = find_js_files(REPO_ROOT)
    findings = scan_innerhtml_assignments(js_files)
    save_baseline(findings)
    print(f'baseline 已更新:{BASELINE_PATH}')
    print(f'记录 innerHTML 赋值 {len(findings)} 处.')
    return 0


def main() -> int:
    """Parse CLI flags and dispatch the raw-innerHTML quality gate.

    Returns:
        Computed result.
    """
    parser = argparse.ArgumentParser(description='raw-innerHTML 阻断 gate')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true', help='增量检查:对比 baseline,发现新增则 BLOCK'
    )
    mode.add_argument('--update-baseline', action='store_true', help='更新 baseline 文件')
    args = parser.parse_args()

    if args.update_baseline:
        return run_update_baseline(args)
    return run_check(args)


if __name__ == '__main__':
    raise SystemExit(main())
