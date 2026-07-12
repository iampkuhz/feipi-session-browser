#!/usr/bin/env python3
"""P0 门禁：检查 legacy-aliases.css 不存在，且全仓库无引用。"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality._trigger import parse_changed_files, skip_if_not_triggered
CSS_DIR = REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'css'
SRC_DIR = REPO_ROOT / 'src'

# 触发模式：当变更文件匹配时运行此检查
TRIGGER_PATTERNS = [
    'java/web/src/main/resources/static/css/**/*.css',
]


# 解析命令行参数并运行脚本入口。
def main() -> None:
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    errors: list[str] = []

    # 检查 1: legacy-aliases.css 文件不存在
    legacy_file = CSS_DIR / 'legacy-aliases.css'
    if legacy_file.exists():
        errors.append(f'[BLOCK] {legacy_file.relative_to(REPO_ROOT)} 必须全删。')

    # 检查 2: 全仓库无引用
    for pattern in ('*.css', '*.html', '*.py', '*.js'):
        for f in SRC_DIR.rglob(pattern):
            text = f.read_text(encoding='utf-8', errors='replace')
            if 'legacy-aliases' in text:
                rel = f.relative_to(REPO_ROOT)
                errors.append(f'[BLOCK] {rel} 仍引用 legacy-aliases。')

    # 检查 3: 不新增 legacy-*alias* 或 compat shim 文件
    if CSS_DIR.exists():
        for f in CSS_DIR.glob('*.css'):
            name = f.name.lower()
            if any(kw in name for kw in ('legacy', 'compat', 'old-ui', 'alias')):
                errors.append(f'[BLOCK] 发现新增兼容层文件: {f.relative_to(REPO_ROOT)}')

    if errors:
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print('[PASS] legacy-aliases.css 已全删，全仓库无引用，无新增兼容层。')
        sys.exit(0)


if __name__ == '__main__':
    main()
