"""Gate 阶段目录、命名、文件规模和 import 方向门禁。"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

GATE_ROOT = Path('scripts/gates')
STAGES = ('catalog', 'planning', 'execution', 'evidence', 'presentation', 'maintenance', 'checks')
RANK = {
    'catalog': 0,
    'planning': 1,
    'execution': 2,
    'evidence': 3,
    'presentation': 3,
    'maintenance': 4,
}
REQUIRED_FUNCTIONS = {
    'capture_change_snapshot',
    'match_trigger',
    'compile_gate_plan',
    'adapt_recipe_step',
    'supervise_process',
    'classify_owner_outcome',
    'orchestrate_gate_run',
    'store_run_receipt',
    'render_terminal_event',
    'audit_gate_health',
}


def _source_files() -> list[Path]:
    return sorted(path for path in GATE_ROOT.rglob('*.py') if '__pycache__' not in path.parts)


def test_root_contains_only_public_entry_and_named_stages() -> None:
    names = {path.name for path in GATE_ROOT.iterdir() if path.name != '__pycache__'}
    assert names == {'cli.py', 'config', *STAGES}
    assert set(STAGES) <= names
    config = GATE_ROOT / 'config'
    assert config.is_dir()
    assert {path.name for path in config.iterdir()} == {'technical-terms.json'}
    assert (config / 'technical-terms.json').is_file()


def test_stage_basenames_are_unique() -> None:
    files = _source_files()
    owners: defaultdict[str, list[Path]] = defaultdict(list)
    for path in files:
        if path.name != '__init__.py':
            owners[path.name].append(path)
    assert {name: paths for name, paths in owners.items() if len(paths) > 1} == {}


def test_stage_files_stay_within_size_budget() -> None:
    assert len((GATE_ROOT / 'cli.py').read_text(encoding='utf-8').splitlines()) <= 250
    for path in _source_files():
        if path.name in {'cli.py', '__init__.py'}:
            continue
        if path.relative_to(GATE_ROOT).parts[0] == 'checks' and path.name not in {
            '__main__.py',
            'check_protocol.py',
            'check_registry.py',
        }:
            continue
        limit = 300 if 'catalog/domains' in path.as_posix() else 400
        assert len(path.read_text(encoding='utf-8').splitlines()) <= limit, path


def test_imports_do_not_reverse_stage_dependencies() -> None:
    violations: list[str] = []
    for path in _source_files():
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


def test_stage_entry_verbs_exist_exactly_once() -> None:
    definitions: defaultdict[str, list[Path]] = defaultdict(list)
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions[node.name].append(path)
    assert {name: len(definitions[name]) for name in REQUIRED_FUNCTIONS} == dict.fromkeys(
        REQUIRED_FUNCTIONS, 1
    )
