#!/usr/bin/env python3
"""检查 JavaScript 中新增的 raw innerHTML 赋值。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckOptions, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repository_root()


BASELINE_PATH = REPO_ROOT / 'scripts' / 'checks' / 'web' / 'baselines' / 'innerhtml_baseline.json'

# 匹配 innerHTML 赋值:element.innerHTML = ...
# 不匹配读取:x = element.innerHTML
INNERHTML_ASSIGN_RE = re.compile(r'\.innerHTML\s*=')

# 匹配注释行(// ... 或 /* ... */)中的 innerHTML,排除纯注释
COMMENT_LINE_RE = re.compile(r'^\s*(?://|/\*|\*)')

# 排除清空操作(.innerHTML = '' 或 .innerHTML = ""),视为安全
CLEAR_ASSIGN_RE = re.compile(r"\.innerHTML\s*=\s*['\"]\s*['\"]")


def find_js_files(root: Path) -> list[Path]:
    """返回静态资源、测试和脚本目录中的 JavaScript 文件。"""
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
    """扫描 innerHTML 赋值并保留用于诊断的源码位置。"""
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
    """加载已批准的违规键；缺失或损坏时返回空集合以保持 fail-closed。"""
    if not BASELINE_PATH.exists():
        return set()
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
        return {entry['file'] + ':' + str(entry['line']) for entry in data.get('entries', [])}
    except (json.JSONDecodeError, KeyError, ValueError):
        return set()


def save_baseline(findings: list[dict]) -> None:
    """保存稳定排序的已审计违规键，不写入扫描正文。"""
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(
            {'version': 1, 'entries': findings, 'count': len(findings)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )


def run_check(args: CheckOptions) -> int:
    """将扫描结果与基线比对，发现任何新增项时返回失败。"""
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
    print(f'存量基线:{known_count} 处(技术债务)')
    print(f'新增 BLOCK:{len(new_items)} 处')
    print()

    if known_count > 0 and os.environ.get('SESSION_BROWSER_SHOW_BASELINE_WARNINGS') == '1':
        print('--- 存量 innerHTML baseline ---')
        for f in findings:
            key = f['file'] + ':' + str(f['line'])
            tag = '[BASELINE]' if key in baseline else '[NEW!!]'
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
        return 0

    # 全量扫描模式
    if not baseline:
        print('提示:首次运行,建议执行 --update-baseline 建立 baseline.')
        print(f'  baseline 路径:{BASELINE_PATH}')
    return 0


def run_update_baseline(args: CheckOptions) -> int:
    """用当前扫描结果更新 baseline 文件。"""
    js_files = find_js_files(REPO_ROOT)
    findings = scan_innerhtml_assignments(js_files)
    save_baseline(findings)
    print(f'baseline 已更新:{BASELINE_PATH}')
    print(f'记录 innerHTML 赋值 {len(findings)} 处.')
    return 0


def main() -> int:
    """解析命令行参数并运行脚本入口。"""
    parser = argument_parser(description='raw-innerHTML 阻断 gate')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true', help='增量检查:对比 baseline,发现新增则 BLOCK'
    )
    mode.add_argument('--update-baseline', action='store_true', help='更新 baseline 文件')
    args = parser.parse_args()

    if args.update_baseline:
        return run_update_baseline(args)
    return run_check(args)
