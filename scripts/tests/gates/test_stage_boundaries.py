"""Gate 阶段 import 方向检查。"""

from __future__ import annotations

import ast
from pathlib import Path

GATE_ROOT = Path('scripts/gates')
RANK = {
    'catalog': 0,
    'planning': 1,
    'execution': 2,
    'evidence': 3,
    'presentation': 3,
    'maintenance': 4,
}


def test_imports_do_not_reverse_stage_dependencies() -> None:
    violations: list[str] = []
    for path in GATE_ROOT.rglob('*.py'):
        relative = path.relative_to(GATE_ROOT)
        source = relative.parts[0]
        if source not in RANK:
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            parts = node.module.split('.')
            if parts[:2] != ['scripts', 'gates'] or len(parts) < 3:
                continue
            target = parts[2]
            if target in RANK and RANK[target] > RANK[source]:
                violations.append(f'{path}: {source} -> {target}')
    assert violations == []
