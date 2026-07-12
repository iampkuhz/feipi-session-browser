#!/usr/bin/env python3
"""提供 validate task files 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'harness/**',
    'openspec/**',
    'skills/**',
]

# 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
changed_files = None
for i, arg in enumerate(sys.argv):
    if arg == '--changed-files' and i + 1 < len(sys.argv):
        changed_files = parse_changed_files(sys.argv[i + 1])
        break
skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

required_checkbox = ['- [ ]', '- [x]']  # 至少需要一个任务复选框
required = [required_checkbox, 'Validation:']
errors = []
for p in (
    (Path.cwd() / 'openspec' / 'changes').rglob('tasks.md')
    if (Path.cwd() / 'openspec' / 'changes').exists()
    else []
):
    if 'archive' in p.parts:
        continue
    text = p.read_text(encoding='utf-8')
    has_checkbox = any(c in text for c in required_checkbox)
    if not has_checkbox:
        errors.append(f'{p}: missing checkbox pattern')
    if 'Validation:' not in text:
        errors.append(f'{p}: missing Validation: lines')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('task files ok')
