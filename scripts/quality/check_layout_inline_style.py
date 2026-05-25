#!/usr/bin/env python3
"""layout-inline-style 阻断 gate。

扫描 HTML 模板和 JS 文件，查找 layout 相关的 inline style，执行以下策略：
- CSS custom property（--segment-width、--fill-width 等）不视为违规
- 存量 layout inline style 标记为 WARN（技术债务）
- 新增 layout inline style 标记为 BLOCK（阻断）

用法：
    # 全量扫描（生成 baseline 或仅报告）
    python3 scripts/quality/check_layout_inline_style.py

    # 增量检查（对比 baseline，发现新增则 BLOCK）
    python3 scripts/quality/check_layout_inline_style.py --check

    # 更新 baseline（在已知安全的新增后手动运行）
    python3 scripts/quality/check_layout_inline_style.py --update-baseline

退出码：
    0 — 无新增 layout inline style（全量扫描始终返回 0）
    1 — 发现新增 layout inline style（--check 模式）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_PATH = REPO_ROOT / "scripts" / "quality" / "layout_inline_style_baseline.json"

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

# CSS custom property 赋值：--xxx:
CSS_CUSTOM_PROPERTY_RE = re.compile(r'\-\-[\w-]+\s*:')

# JS 中 .style.xxx 赋值模式（如 .style.display = ）
JS_STYLE_ASSIGN_RE = re.compile(r'\.style\.(display|position|flex|grid|width|height|minWidth|minHeight|maxWidth|maxHeight|top|left|right|bottom|padding|paddingTop|paddingRight|paddingBottom|paddingLeft|margin|marginTop|marginRight|marginBottom|marginLeft|overflow|overflowX|overflowY|zIndex)\s*=')

# JS 注释行
JS_COMMENT_LINE_RE = re.compile(r"^\s*(?://|/\*|\*)")


def find_html_files(root: Path) -> list[Path]:
    """递归查找所有 HTML 模板文件。"""
    templates_dir = root / "src" / "session_browser" / "web" / "templates"
    results: list[Path] = []
    if templates_dir.is_dir():
        results.extend(sorted(templates_dir.rglob("*.html")))
    return results


def find_js_files(root: Path) -> list[Path]:
    """递归查找所有 JS 文件。"""
    js_dirs = [
        root / "src" / "session_browser" / "web" / "static" / "js",
    ]
    results: list[Path] = []
    for d in js_dirs:
        if d.is_dir():
            results.extend(sorted(d.rglob("*.js")))
    return results


def scan_html_inline_styles(html_files: list[Path]) -> list[dict]:
    """扫描 HTML 文件中 layout 相关的 inline style。

    排除仅包含 CSS custom property 的 style 属性。
    """
    findings: list[dict] = []
    for html_file in html_files:
        try:
            text = html_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel_path = str(html_file.relative_to(REPO_ROOT))

        # 匹配 style="..." 或 style='...'
        # 不捕获 {{ grid_style }} 这类模板变量注入
        style_attr_re = re.compile(r'style\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)

        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # 跳过纯注释行
            if stripped.startswith("{#") or stripped.startswith("<!--"):
                continue

            for match in style_attr_re.finditer(line):
                style_value = match.group(1)

                # 跳过纯模板变量（如 {{ grid_style }}）
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
                    findings.append({
                        "file": rel_path,
                        "line": line_no,
                        "source": "html",
                        "snippet": stripped[:140],
                    })
    return findings


def scan_js_style_assignments(js_files: list[Path]) -> list[dict]:
    """扫描 JS 文件中 .style.xxx 布局属性赋值。"""
    findings: list[dict] = []
    for js_file in js_files:
        try:
            text = js_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel_path = str(js_file.relative_to(REPO_ROOT))
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # 跳过注释行
            if JS_COMMENT_LINE_RE.match(stripped):
                continue
            if JS_STYLE_ASSIGN_RE.search(line):
                findings.append({
                    "file": rel_path,
                    "line": line_no,
                    "source": "js",
                    "snippet": stripped[:140],
                })
    return findings


def load_baseline() -> set[str]:
    """加载 baseline，返回已知违规位置的集合。"""
    if not BASELINE_PATH.exists():
        return set()
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return {entry["file"] + ":" + str(entry["line"]) for entry in data.get("entries", [])}
    except (json.JSONDecodeError, KeyError, ValueError):
        return set()


def save_baseline(findings: list[dict]) -> None:
    """将当前扫描结果保存为 baseline。"""
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps({"version": 1, "entries": findings, "count": len(findings)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_all_scans() -> list[dict]:
    """执行全部扫描，合并 HTML 和 JS 结果。"""
    html_files = find_html_files(REPO_ROOT)
    js_files = find_js_files(REPO_ROOT)
    findings: list[dict] = []
    findings.extend(scan_html_inline_styles(html_files))
    findings.extend(scan_js_style_assignments(js_files))
    return findings


def run_check(args: argparse.Namespace) -> int:
    findings = run_all_scans()
    baseline = load_baseline()
    known_count = 0
    new_items: list[dict] = []

    for f in findings:
        key = f["file"] + ":" + str(f["line"])
        if key in baseline:
            known_count += 1
        else:
            new_items.append(f)

    total = len(findings)

    print(f"=== layout-inline-style 阻断 gate ===")
    print(f"HTML 模板文件数：{len(find_html_files(REPO_ROOT))}")
    print(f"JS 文件数：{len(find_js_files(REPO_ROOT))}")
    print(f"layout inline style 总数：{total}")
    print(f"存量 WARN：{known_count} 处（技术债务）")
    print(f"新增 BLOCK：{len(new_items)} 处")
    print()

    if known_count > 0:
        print("--- 存量 layout inline style（WARN）---")
        for f in findings:
            key = f["file"] + ":" + str(f["line"])
            if key in baseline:
                tag = "[WARN]"
            else:
                tag = "[NEW!!]"
            src_tag = f"[{f['source'].upper()}]"
            print(f"  {tag} {src_tag} {f['file']}:{f['line']} | {f['snippet']}")
        print()

    if new_items:
        print("!!! 新增 layout inline style（BLOCK） !!!")
        for f in new_items:
            src_tag = f"[{f['source'].upper()}]"
            print(f"  [BLOCK] {src_tag} {f['file']}:{f['line']} | {f['snippet']}")
        print()
        print("结论：FAIL — 检测到新增 layout inline style，违反 layout-inline-style 阻断策略。")
        print("请移除 inline style 并改用 CSS class 或 CSS custom property。")
        return 1

    if args.check:
        print("结论：PASS — 无新增 layout inline style。")
        return 0

    # 全量扫描模式
    print("结论：PASS（全量扫描）— 存量技术债务已记录。")
    if not baseline:
        print(f"提示：首次运行，建议执行 --update-baseline 建立 baseline。")
        print(f"  baseline 路径：{BASELINE_PATH}")
    return 0


def run_update_baseline(args: argparse.Namespace) -> int:
    findings = run_all_scans()
    save_baseline(findings)
    print(f"baseline 已更新：{BASELINE_PATH}")
    print(f"记录 layout inline style {len(findings)} 处。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="layout-inline-style 阻断 gate")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="增量检查：对比 baseline，发现新增则 BLOCK")
    mode.add_argument("--update-baseline", action="store_true", help="更新 baseline 文件")
    args = parser.parse_args()

    if args.update_baseline:
        return run_update_baseline(args)
    return run_check(args)


if __name__ == "__main__":
    raise SystemExit(main())
