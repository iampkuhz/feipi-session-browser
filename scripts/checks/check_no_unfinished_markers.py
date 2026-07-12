#!/usr/bin/env python3
"""提供 检查 no unfinished markers 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'java/**/*.java',
    'scripts/**/*.py',
    'tests/**/*.py',
]

# 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
changed_files = None
for i, arg in enumerate(sys.argv):
    if arg == '--changed-files' and i + 1 < len(sys.argv):
        changed_files = parse_changed_files(sys.argv[i + 1])
        break
skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

bad = ['TODO', 'FIXME', 'TBD', 'PLACEHOLDER', 'STUB']
skip = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'scripts/checks'}
violations = []
script_dir = Path(__file__).parent
for p in Path.cwd().rglob('*'):
    if any(part in skip for part in p.parts) or not p.is_file():
        continue
    if p.is_relative_to(script_dir):
        continue
    if p.suffix.lower() not in {
        '.md',
        '.py',
        '.js',
        '.ts',
        '.html',
        '.css',
        '.json',
        '.yaml',
        '.yml',
    }:
        continue
    try:
        text = p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    for marker in bad:
        if marker in text:
            violations.append(f'{p}: contains {marker}')
if violations:
    print('\n'.join(violations))
    sys.exit(1)
print('no unfinished markers')
