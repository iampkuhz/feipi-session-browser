"""Typed Gate catalog 的 schema、tier 与唯一性 contract。"""

from dataclasses import FrozenInstanceError

import pytest
from scripts.gates.catalog import CATALOG, GATES, gate_by_name, tier_by_name
from scripts.gates.planner import gates_for_tier, validate_catalog


def test_catalog_schema_is_complete_unique_and_acyclic() -> None:
    validate_catalog()
    assert len(GATES) == 59
    assert len({gate.name for gate in GATES}) == 59
    for gate in GATES:
        assert gate.targets
        assert gate.executor_type
        assert bool(gate.command) != bool(gate.gradle_tasks)
        assert gate.timeout_seconds > 0
        assert isinstance(gate.parallel_safe, bool)
        assert isinstance(gate.exclusive_resources, tuple)
        assert gate.incremental_mode
        assert gate.changed_files_input
        assert isinstance(gate.included_by, tuple)
        assert 'full' in gate.tiers
        assert gate.receipt_policy
        assert gate.description.endswith('。')


def test_catalog_models_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        GATES[0].name = 'mutated'  # type: ignore[misc]


def test_catalog_defines_nested_tiers() -> None:
    assert [tier_by_name(name).name for name in ('quick', 'required', 'full')] == [
        'quick',
        'required',
        'full',
    ]
    assert gates_for_tier('quick') < gates_for_tier('required')


def test_full_only_gate_is_catalog_driven() -> None:
    gate = gate_by_name('javaApiSnapshot')
    assert gate.tiers == ('full',)
    assert gate.name not in gates_for_tier('required')
    assert gate.name in gates_for_tier('full')


def test_catalog_is_the_only_gate_truth() -> None:
    assert CATALOG.gates is GATES


def test_changed_files_process_input_is_explicit_and_minimal() -> None:
    supported = {gate.name for gate in GATES if gate.changed_files_input.value != 'none'}
    assert supported == {
        'languagePolicy',
        'javaRecordComponentJavadocs',
        'reuseStandardCpd',
    }


def test_exclusive_resources_follow_gate_capability_not_target_union() -> None:
    """共享 pytest 不得占用其内部 contract 还会获取的浏览器资源。"""
    assert gate_by_name('pytest').exclusive_resources == ()
    assert gate_by_name('browserLayout').exclusive_resources == (
        'fixture-server',
        'playwright-browser',
    )
    assert gate_by_name('javaCheck').exclusive_resources == (
        'gradle-daemon',
        'java-build-tree',
    )
