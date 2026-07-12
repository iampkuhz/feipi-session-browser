#!/usr/bin/env python3
"""本模块负责执行 `validate_layout` 对应的确定性仓库检查。

不负责修改业务代码；由 OpenSpec 命令行或 required Gate 调用。"""

import sys
from pathlib import Path

root = Path.cwd() / 'openspec'
errors = []
if not (root / 'specs').is_dir():
    errors.append('openspec/specs missing')
if not (root / 'changes').is_dir():
    errors.append('openspec/changes missing')
for change in (root / 'changes').glob('*') if (root / 'changes').exists() else []:
    if change.name == 'archive' or not change.is_dir():
        continue
    for f in ['proposal.md', 'tasks.md']:
        if not (change / f).exists():
            errors.append(f'{change}/{f} missing')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('repo structure ok')
