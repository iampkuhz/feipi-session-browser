#!/usr/bin/env python3
"""CSS smoke checks for Java sessions list API-first shell."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _api_first_checklib import CSS, LEGACY_PY_ROOT, LEGACY_STATIC_ROOT, exists, has_all, has_none, read, run


# 检查 CSS 是否包含未归一化的裸色值。
def no_bare_hex(css: str) -> tuple[bool, str]:
    """参数：
        css: 待检查的 CSS 文本。

    返回：
        是否通过和说明文本。
    """
    allowed = {'#fff', '#ffffff', '#000', '#000000'}
    hits = sorted(set(re.findall(r'#[0-9a-fA-F]{3,8}\b', css)) - allowed)
    return not hits, 'clean' if not hits else 'bare hex: ' + ', '.join(hits[:8])


# 运行 Sessions 列表 CSS 契约检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    css_path = CSS / 'sessions-list.css'
    css = read(css_path)
    checks = [
        ('sessions-list.css exists', lambda: exists(css_path)),
        ('no @import', lambda: has_none(css, ['@import'])),
        ('uses page-specific selectors', lambda: has_all(css, ['.sessions-page', '.sessions-table-card', '.sessions-filter-select'])),
        ('uses shared token variables/classes', lambda: has_all(css + read(CSS / 'tokens.css') + read(CSS / 'ui-primitives.css'), ['--token-input-fresh', '--token-cache-read', '.tokenbar-seg'])),
        ('has responsive rules', lambda: has_all(css, ['@media', 'max-width'])),
        ('no legacy Python paths', lambda: has_none(css, [LEGACY_PY_ROOT, LEGACY_STATIC_ROOT])),
    ]
    return run('sessions-list.css Java API-first QA checks', checks)


if __name__ == '__main__':
    raise SystemExit(main())
