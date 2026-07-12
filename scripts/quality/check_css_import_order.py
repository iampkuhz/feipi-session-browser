#!/usr/bin/env python3
"""CSS @import 顺序检查。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality._trigger import parse_changed_files, skip_if_not_triggered

CSS_DIR = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'css'

# 触发模式：当变更文件匹配时运行此检查
TRIGGER_PATTERNS = [
    'java/web/src/main/resources/static/css/**/*.css',
]


# 检查CSS import order。
def check_css_import_order(css_path: Path) -> list[str]:
    """参数：
        css_path: 待检查的路径。

    返回：
        结果列表。

    说明：
        规则：。
        1. @import 必须出现在任何 selector { rule } 之前。
        2. 允许 @charset 在 import 之前。
        3. 允许 @layer statement（无 body）在 import 之前。
        4. 注释不视为 rule。
        返回错误列表。
    """
    errors: list[str] = []
    rel = css_path.relative_to(REPO_ROOT).as_posix()
    text = css_path.read_text(encoding='utf-8', errors='replace')

    # 移除注释
    text_no_comments = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)

    lines = text_no_comments.split('\n')

    # 跟踪是否在 { } 内部（多行 rule）
    in_block = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        # 计数括号
        open_braces = stripped.count('{')
        close_braces = stripped.count('}')
        # 检查是否是 @import
        if stripped.startswith('@import') and in_block == 0:
            continue

        # 检查是否是 @charset 或 @layer statement（允许在 import 前）
        if stripped.startswith('@charset'):
            continue
        if stripped.startswith('@layer') and '{' not in stripped and '}' not in stripped:
            continue

        in_block += open_braces - close_braces
        in_block = max(in_block, 0)  # safety

    # 第二种检查方式：找 @import 出现在 { 之后的情况
    # 移除注释后，检查是否有 rule body 后出现 @import
    pattern = re.compile(
        r'\{[^}]*(?:\}|$).*?@import\s',
        re.DOTALL,
    )
    match = pattern.search(text_no_comments)
    if match:
        # 计算行号
        line_num = text_no_comments[: match.start()].count('\n') + 1
        errors.append(
            f'{rel}:{line_num}: @import 出现在 style rule 之后，浏览器会忽略 rule 之后的 @import。'
        )

    return errors


# 解析命令行参数并运行脚本入口。
def main() -> None:
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    if not CSS_DIR.exists():
        print(f'[BLOCK] CSS 目录不存在: {CSS_DIR}')
        sys.exit(1)

    all_errors: list[str] = []
    css_files = sorted(CSS_DIR.rglob('*.css'))

    for css_path in css_files:
        errs = check_css_import_order(css_path)
        all_errors.extend(errs)

    if all_errors:
        print(f'[BLOCK] 发现 {len(all_errors)} 个 @import 顺序错误：')
        for err in all_errors:
            print(f'  {err}')
        sys.exit(1)
    else:
        print(f'[PASS] 全部 {len(css_files)} 个 CSS 文件 @import 顺序正确。')
        sys.exit(0)


if __name__ == '__main__':
    main()
