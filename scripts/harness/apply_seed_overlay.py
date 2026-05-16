#!/usr/bin/env python3
from pathlib import Path
import shutil, sys
seed = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path('~/Downloads/feipi_session_browser_harness_seed2').expanduser().resolve()
overlay = seed / 'seed-overlay'
if not overlay.is_dir():
    raise SystemExit(f'seed overlay not found: {overlay}')
root = Path.cwd().resolve()
for src in overlay.rglob('*'):
    rel = src.relative_to(overlay)
    dst = root / rel
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
    elif not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    else:
        print(f'skip existing: {rel}')
print('overlay copy completed; inspect skipped files and merge manually')
