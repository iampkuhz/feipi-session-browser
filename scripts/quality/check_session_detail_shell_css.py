#!/usr/bin/env python3
"""提供 检查 session detail shell CSS 脚本能力。"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality._trigger import parse_changed_files, skip_if_not_triggered
SHELL_CSS = (
    REPO_ROOT / 'java' / 'web' / 'src' / 'main' / 'resources' / 'static' / 'css' / 'shell.css'
)

FAILURES = []

# 触发模式：当变更文件匹配时运行此检查
TRIGGER_PATTERNS = [
    'java/web/src/main/resources/static/**',
    'java/web/src/main/resources/templates/**',
]


# 维护fail。
def fail(msg: str) -> None:
    """参数：
        msg: msg 参数。
    """
    FAILURES.append(msg)
    print(f'  FAIL: {msg}')


# 标记检查通过。
def ok(msg: str) -> None:
    """参数：
        msg: msg 参数。
    """
    print(f'  OK:   {msg}')


# 维护检查。
def check(content: str) -> None:
    """参数：
        content: 要写入的文本内容。
    """
    if (
        'body.hide-left .shell.phase1-shell' in content
        or 'body.hide-left .shell.no-inspector.phase1-shell' in content
    ):
        ok('High-specificity body.hide-left .shell.phase1-shell override exists')
    else:
        fail(
            "Missing 'body.hide-left .shell.phase1-shell' (or .no-inspector.variant) "
            '— cascade conflict will not be resolved when sidebar is collapsed'
        )

    if '.shell.phase1-shell .main' in content:
        ok('.shell.phase1-shell .main rule exists')
    else:
        fail("Missing '.shell.phase1-shell .main' rule")

    if 'grid-column: 1 / -1' in content or 'grid-column:1/-1' in content:
        ok('grid-column: 1 / -1 found (prevents auto-placement into 0px column)')
    else:
        fail("Missing 'grid-column: 1 / -1' — .main may auto-place into 0px column")

    if 'width: 100%' in content or 'width:100%' in content:
        ok('width: 100% found on .main')
    else:
        fail("Missing 'width: 100%' on .main")

    if 'min-width: 0' in content or 'min-width:0' in content:
        ok('min-width: 0 found on .main')
    else:
        fail("Missing 'min-width: 0' on .main")

    # 检查如果 there's a standalone .shell.phase1-shell { grid-template-columns }。
    standalone_pattern = r'\.shell\.phase1-shell\s*\{[^}]*grid-template-columns'
    has_standalone = bool(re.search(standalone_pattern, content))

    hide_left_pattern = r'body\.hide-left.*\.shell\.phase1-shell'
    has_hide_left_override = bool(re.search(hide_left_pattern, content))

    if has_standalone and not has_hide_left_override:
        fail(
            "Only low-specificity '.shell.phase1-shell' grid rule exists "
            'without body.hide-left override — will be overridden in collapsed sidebar state'
        )
    elif has_hide_left_override:
        ok('High-specificity override prevents cascade conflict in all body states')


# 解析命令行参数并运行脚本入口。
def main() -> None:
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    print('=' * 60)
    print('Session Detail Shell CSS Firewall Check')
    print('=' * 60)

    if not SHELL_CSS.exists():
        print(f'ERROR: shell.css not found at {SHELL_CSS}')
        sys.exit(2)

    content = SHELL_CSS.read_text()
    print(f'\nChecking {SHELL_CSS.relative_to(REPO_ROOT)}\n')

    check(content)

    print()
    if FAILURES:
        print(f'FAILED: {len(FAILURES)} rule(s) missing')
        for f in FAILURES:
            print(f'  - {f}')
        sys.exit(1)
    else:
        print('PASS: All CSS firewall rules present')
        sys.exit(0)


if __name__ == '__main__':
    main()
