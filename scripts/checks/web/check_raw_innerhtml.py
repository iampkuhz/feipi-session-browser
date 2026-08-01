"""检查 JavaScript 是否新增 raw innerHTML 赋值。

已审计基线只容纳存量位置，新增赋值必须改用安全文本或转义渲染。唯一公开入口是
`check(arguments)`；失败表示扫描结果出现基线外条目，`--update-baseline` 仍显式更新原基线。
"""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckOptions, CheckResult, argument_parser, repository_root

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


def _find_js_files(root: Path) -> list[Path]:
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


def _scan_innerhtml_assignments(js_files: list[Path]) -> list[dict]:
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


def _load_baseline() -> set[str]:
    """加载已批准的违规键；缺失或损坏时返回空集合以保持 fail-closed。"""
    if not BASELINE_PATH.exists():
        return set()
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding='utf-8'))
        return {entry['file'] + ':' + str(entry['line']) for entry in data.get('entries', [])}
    except (json.JSONDecodeError, KeyError, ValueError):
        return set()


def _save_baseline(findings: list[dict]) -> None:
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


def _run_check(args: CheckOptions) -> list[str]:
    """将扫描结果与基线比对，按原有诊断顺序返回新增项。"""
    js_files = _find_js_files(REPO_ROOT)
    if not js_files:
        return []

    findings = _scan_innerhtml_assignments(js_files)
    baseline = _load_baseline()
    known_count = 0
    new_items: list[dict] = []
    for finding in findings:
        key = finding['file'] + ':' + str(finding['line'])
        if key in baseline:
            known_count += 1
        else:
            new_items.append(finding)

    clear_count = sum(1 for finding in findings if finding['isClear'])
    lines = [
        '=== raw-innerHTML 阻断 gate ===',
        f'扫描文件数:{len(js_files)}',
        f'innerHTML 赋值总数:{len(findings)}(含清空操作 {clear_count} 处)',
        f'存量基线:{known_count} 处(技术债务)',
        f'新增 BLOCK:{len(new_items)} 处',
        '',
    ]

    if known_count > 0 and os.environ.get('SESSION_BROWSER_SHOW_BASELINE_WARNINGS') == '1':
        lines.append('--- 存量 innerHTML baseline ---')
        for finding in findings:
            key = finding['file'] + ':' + str(finding['line'])
            tag = '[BASELINE]' if key in baseline else '[NEW!!]'
            clear_tag = ' (清空)' if finding['isClear'] else ''
            lines.append(
                f'  {tag} {finding["file"]}:{finding["line"]}{clear_tag} | {finding["snippet"]}'
            )
        lines.append('')

    if not new_items:
        return []

    lines.append('!!! 新增 innerHTML 使用(BLOCK) !!!')
    for finding in new_items:
        lines.append(f'  [BLOCK] {finding["file"]}:{finding["line"]} | {finding["snippet"]}')
    lines.extend(
        [
            '',
            '结论:FAIL — 检测到新增 innerHTML 赋值,违反 raw-innerHTML 阻断策略.',
            '如需豁免,请先修复为 textContent 或 escapeHtml(),或经审阅后运行 --update-baseline.',
        ]
    )
    return lines


def _run_update_baseline(args: CheckOptions) -> list[str]:
    """用当前扫描结果更新 baseline 文件。"""
    js_files = _find_js_files(REPO_ROOT)
    findings = _scan_innerhtml_assignments(js_files)
    _save_baseline(findings)
    return []


def check(arguments: list[str]) -> CheckResult:
    """解析扫描模式，并按摘要、基线明细、BLOCK 明细顺序返回失败。"""
    parser = argument_parser(description='raw-innerHTML 阻断 gate')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true', help='增量检查:对比 baseline,发现新增则 BLOCK'
    )
    mode.add_argument('--update-baseline', action='store_true', help='更新 baseline 文件')
    args = parser.parse_args(arguments)

    if args.update_baseline:
        return CheckResult.from_errors(_run_update_baseline(args))
    return CheckResult.from_errors(_run_check(args))
