#!/usr/bin/env python3
"""负责检查模板与脚本中新引入的布局 inline style。

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


BASELINE_PATH = (
    REPO_ROOT / 'scripts' / 'checks' / 'web' / 'baselines' / 'layout_inline_style_baseline.json'
)

# layout 相关 CSS 属性关键字
LAYOUT_PROPERTIES = re.compile(
    r'\b(display|position|flex|grid|width|height|min-width|min-height|max-width|max-height'
    r'|top|left|right|bottom'
    r'|padding|padding-top|padding-right|padding-bottom|padding-left'
    r'|margin|margin-top|margin-right|margin-bottom|margin-left'
    r'|overflow|overflow-x|overflow-y'
    r'|z-index'
    r')\s*:',
    re.IGNORECASE,
)

# 匹配 CSS custom property 赋值，确保扫描可识别设计 token 变量声明。
CSS_CUSTOM_PROPERTY_RE = re.compile(r'\-\-[\w-]+\s*:')

# 匹配 JS 中直接写入布局 style 属性的赋值模式。
JS_STYLE_ASSIGN_RE = re.compile(
    r'\.style\.(display|position|flex|grid|width|height|minWidth|minHeight|maxWidth|maxHeight|top|left|right|bottom|padding|paddingTop|paddingRight|paddingBottom|paddingLeft|margin|marginTop|marginRight|marginBottom|marginLeft|overflow|overflowX|overflowY|zIndex)\s*='
)

# JS 注释行
JS_COMMENT_LINE_RE = re.compile(r'^\s*(?://|/\*|\*)')


def find_html_files(root: Path) -> list[Path]:
    """返回仓库模板目录中的 HTML 文件。"""
    templates_dir = root / 'java' / 'web' / 'src' / 'main' / 'resources' / 'templates'
    results: list[Path] = []
    if templates_dir.is_dir():
        results.extend(sorted(templates_dir.rglob('*.html')))
    return results


def find_js_files(root: Path) -> list[Path]:
    """返回仓库静态资源目录中的 JavaScript 文件。"""
    js_dirs = [
        root / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'js',
    ]
    results: list[Path] = []
    for d in js_dirs:
        if d.is_dir():
            results.extend(sorted(d.rglob('*.js')))
    return results


def scan_html_inline_styles(html_files: list[Path]) -> list[dict]:
    """扫描 HTML 中包含布局属性的 inline style。"""
    findings: list[dict] = []
    for html_file in html_files:
        try:
            text = html_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        rel_path = str(html_file.relative_to(REPO_ROOT))

        # 匹配 style="..." 或 style='...'
        # 不捕获 {{ grid_style }} 这类模板变量注入
        style_attr_re = re.compile(r'style\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # 跳过纯注释行
            if stripped.startswith('{#') or stripped.startswith('<!--'):
                continue

            for match in style_attr_re.finditer(line):
                style_value = match.group(1)

                # 跳过纯模板变量(如 {{ grid_style }})
                if re.match(r'^\s*\{\{.*\}\}\s*$', style_value):
                    continue

                # 检查是否包含 CSS custom property
                has_custom_prop = bool(CSS_CUSTOM_PROPERTY_RE.search(style_value))
                if has_custom_prop:
                    # 提取非 custom property 部分再检查
                    non_custom = CSS_CUSTOM_PROPERTY_RE.sub('', style_value).strip()
                    # 去除分隔符和空白
                    non_custom = re.sub(r'[;\s]+', ' ', non_custom).strip()
                    if not non_custom or not LAYOUT_PROPERTIES.search(non_custom):
                        continue

                if LAYOUT_PROPERTIES.search(style_value):
                    findings.append(
                        {
                            'file': rel_path,
                            'line': line_no,
                            'source': 'html',
                            'snippet': stripped[:140],
                        }
                    )
    return findings


def scan_js_style_assignments(js_files: list[Path]) -> list[dict]:
    """扫描 JavaScript 中直接写入布局 style 属性的语句。"""
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
            if JS_COMMENT_LINE_RE.match(stripped):
                continue
            if JS_STYLE_ASSIGN_RE.search(line):
                findings.append(
                    {
                        'file': rel_path,
                        'line': line_no,
                        'source': 'js',
                        'snippet': stripped[:140],
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


def run_all_scans() -> list[dict]:
    """汇总 HTML 与 JavaScript 的布局 inline style 扫描结果。"""
    html_files = find_html_files(REPO_ROOT)
    js_files = find_js_files(REPO_ROOT)
    findings: list[dict] = []
    findings.extend(scan_html_inline_styles(html_files))
    findings.extend(scan_js_style_assignments(js_files))
    return findings


def run_check(args: CheckOptions) -> int:
    """将扫描结果与基线比对，发现任何新增项时返回失败。"""
    findings = run_all_scans()
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

    print('=== layout-inline-style 阻断 gate ===')
    print(f'HTML 模板文件数:{len(find_html_files(REPO_ROOT))}')
    print(f'JS 文件数:{len(find_js_files(REPO_ROOT))}')
    print(f'layout inline style 总数:{total}')
    print(f'存量基线:{known_count} 处(技术债务)')
    print(f'新增 BLOCK:{len(new_items)} 处')
    print()

    if known_count > 0 and os.environ.get('SESSION_BROWSER_SHOW_BASELINE_WARNINGS') == '1':
        print('--- 存量 layout inline style baseline ---')
        for f in findings:
            key = f['file'] + ':' + str(f['line'])
            tag = '[BASELINE]' if key in baseline else '[NEW!!]'
            src_tag = f'[{f["source"].upper()}]'
            print(f'  {tag} {src_tag} {f["file"]}:{f["line"]} | {f["snippet"]}')
        print()

    if new_items:
        print('!!! 新增 layout inline style(BLOCK) !!!')
        for f in new_items:
            src_tag = f'[{f["source"].upper()}]'
            print(f'  [BLOCK] {src_tag} {f["file"]}:{f["line"]} | {f["snippet"]}')
        print()
        print('结论:FAIL — 检测到新增 layout inline style,违反 layout-inline-style 阻断策略.')
        print('请移除 inline style 并改用 CSS class 或 CSS custom property.')
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
    findings = run_all_scans()
    save_baseline(findings)
    print(f'baseline 已更新:{BASELINE_PATH}')
    print(f'记录 layout inline style {len(findings)} 处.')
    return 0


def main() -> int:
    """解析命令行参数并运行脚本入口。"""
    parser = argument_parser(description='layout-inline-style 阻断 gate')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--check', action='store_true', help='增量检查:对比 baseline,发现新增则 BLOCK'
    )
    mode.add_argument('--update-baseline', action='store_true', help='更新 baseline 文件')
    args = parser.parse_args()

    if args.update_baseline:
        return run_update_baseline(args)
    return run_check(args)
