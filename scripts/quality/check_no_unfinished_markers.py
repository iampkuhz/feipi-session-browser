#!/usr/bin/env python3
from pathlib import Path
import sys
bad = ['TODO', 'FIXME', 'TBD', 'PLACEHOLDER', 'STUB']
skip = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'scripts/quality'}
violations=[]
script_dir = Path(__file__).parent
for p in Path.cwd().rglob('*'):
    if any(part in skip for part in p.parts) or not p.is_file(): continue
    if p.is_relative_to(script_dir): continue
    if p.suffix.lower() not in {'.md','.py','.js','.ts','.html','.css','.json','.yaml','.yml'}: continue
    try: text=p.read_text(encoding='utf-8')
    except UnicodeDecodeError: continue
    for marker in bad:
        if marker in text:
            violations.append(f'{p}: contains {marker}')
if violations:
    print('\n'.join(violations)); sys.exit(1)
print('no unfinished markers')
