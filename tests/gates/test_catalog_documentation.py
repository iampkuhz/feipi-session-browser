"""Catalog 模块的术语、责任分片和维护文档契约。"""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.gates.catalog.gate_contracts import RecipeStepKind
from scripts.gates.catalog.registry import GATES, TARGET_PRESETS

ROOT = Path(__file__).resolve().parents[2]
CATALOG_ROOT = ROOT / 'scripts' / 'gates' / 'catalog'
DOMAIN_ROOT = CATALOG_ROOT / 'domains'


def test_catalog_has_six_named_domain_declarations() -> None:
    assert {path.name for path in DOMAIN_ROOT.glob('*.py')} == {
        '__init__.py',
        'python_toolchain.py',
        'repository_rules.py',
        'agent_harness.py',
        'web_interface.py',
        'java_build.py',
        'session_pipeline.py',
    }
    assert len(TARGET_PRESETS) == 6
    assert len(GATES) == 20


def test_domain_declarations_are_small_and_only_declare_gates() -> None:
    for path in DOMAIN_ROOT.glob('*.py'):
        assert len(path.read_text(encoding='utf-8').splitlines()) <= 300
        if path.name == '__init__.py':
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'))
        assignments = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert assignments == {'GATES'}, path


def test_gate_descriptions_and_recipe_owners_are_explanatory() -> None:
    for gate in GATES:
        assert len(gate.description) >= 12
        assert gate.description.endswith('。')
        assert gate.recipe.steps
        for step in gate.recipe.steps:
            assert isinstance(step.kind, RecipeStepKind)
            assert step.name


def test_catalog_uses_frozen_vocabulary_and_no_generic_module_names() -> None:
    forbidden_basenames = {
        'model.py',
        'support.py',
        'utils.py',
        'definitions.py',
        'planner.py',
        'executor.py',
        'report.py',
        'process.py',
        'health.py',
    }
    paths = tuple(CATALOG_ROOT.rglob('*.py'))
    assert not ({path.name for path in paths} & forbidden_basenames)
    content = '\n'.join(path.read_text(encoding='utf-8') for path in paths)
    assert 'leaf' not in content.lower()
    assert 'RunStep' not in content
    assert 'TargetSpec' not in content
