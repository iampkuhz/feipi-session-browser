#!/usr/bin/env python3
from pathlib import Path
p = Path('docs/ui/hifi')
print('ui hifi directory:', 'ok' if p.exists() else 'missing')
