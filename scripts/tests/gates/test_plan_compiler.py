"""Unique GatePlan compilation and Trigger characterization contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.gates.catalog.registry import GATES, gate_by_name
from scripts.gates.planning.change_snapshot import ChangeSnapshot
from scripts.gates.planning.plan_compiler import (
    CommandInvocation,
    compile_gate_plan,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scripts.gates.catalog.gate_contracts import Gate, RecipeStep


def _snapshot(*files: str, source: str = 'explicit-changed-files') -> ChangeSnapshot:
    return ChangeSnapshot(source, 'head-sha', None, files, 'content-fingerprint')


def test_full_and_selectors_preserve_catalog_order_and_single_recipe() -> None:
    full = compile_gate_plan(_snapshot(source='full'), mode='full')
    target = compile_gate_plan(_snapshot(source='full'), mode='full', target='java-build')
    gate = compile_gate_plan(_snapshot(source='full'), mode='full', gate='browserTests')

    assert full.gates == GATES
    assert tuple(item.name for item in target.gates) == (
        'javaBuildVerification',
        'javaDuplicationAudit',
    )
    assert gate.gates == (gate_by_name('browserTests'),)
    assert target.selector_kind == 'target'
    assert target.selector_value == 'java-build'
    assert gate.selector_kind == 'gate'


def test_empty_incremental_plan_is_representable_but_selector_requires_full() -> None:
    empty = compile_gate_plan(_snapshot())
    assert empty.gates == ()
    assert empty.process_count == 0
    assert len(empty.not_triggered) == len(GATES)
    assert {item.reason for item in empty.not_triggered} == {'no-trigger-pattern-matched'}

    with pytest.raises(ValueError, match='use full mode'):
        compile_gate_plan(_snapshot(), gate='browserTests')
    with pytest.raises(ValueError, match='use full mode'):
        compile_gate_plan(_snapshot(), target='web-interface')


def test_plan_mode_must_match_snapshot_source() -> None:
    with pytest.raises(ValueError, match='full snapshot'):
        compile_gate_plan(_snapshot(), mode='full')
    with pytest.raises(ValueError, match='incremental ChangeSnapshot'):
        compile_gate_plan(_snapshot(source='full'))


def test_selector_exclusions_are_not_reported_as_execution_results() -> None:
    plan = compile_gate_plan(_snapshot('README.md'), gate='javaBuildVerification')
    assert plan.gates == (gate_by_name('javaBuildVerification'),)
    assert all(item.reason == 'excluded-by-selector' for item in plan.not_triggered)
    assert 'javaBuildVerification' not in {item.gate_name for item in plan.not_triggered}


def test_invocation_factory_must_preserve_gate_and_step_ownership() -> None:
    def wrong_owner(gate: Gate, step: RecipeStep) -> Iterable[CommandInvocation]:
        yield CommandInvocation('id', 'command', ('true',), (), 'wrong', step.name)

    with pytest.raises(ValueError, match='wrong Gate'):
        compile_gate_plan(
            _snapshot('scripts/a.py'),
            gate='scriptToolchainQuality',
            invocation_factory=wrong_owner,
        )


@pytest.mark.parametrize(
    ('kwargs', 'message'),
    [
        ({'target': 'missing'}, 'unknown TargetPreset'),
        ({'gate': 'missing'}, 'unknown Gate'),
        (
            {'target': 'java-source', 'gate': 'javaBuildVerification'},
            'mutually exclusive',
        ),
        ({'mode': 'quick'}, 'quick'),
    ],
)
def test_invalid_mode_or_selector_fails_closed(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compile_gate_plan(_snapshot('README.md'), **kwargs)  # type: ignore[arg-type]
