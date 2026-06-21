#!/usr/bin/env python3
"""P0 门禁：检查 legacy-aliases.css 不存在，且全仓库无引用。

用法:
    python3 scripts/quality/check_no_legacy_css.py

退出码:
    0 — 通过
    1 — 发现遗留 CSS
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS_DIR = REPO_ROOT / 'src' / 'session_browser' / 'web' / 'static' / 'css'
SRC_DIR = REPO_ROOT / 'src'


def main() -> None:
    """Run the legacy CSS deletion and reference contract check."""
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
