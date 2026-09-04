"""Unique GatePlan compilation and Trigger characterization contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from scripts.gates.catalog.gate_contracts import Gate, RecipeStep, RecipeStepKind
from scripts.gates.catalog.registry import GATES, gate_by_name
from scripts.gates.planning.change_snapshot import ChangeSnapshot
from scripts.gates.planning.plan_compiler import (
    CommandInvocation,
    compile_gate_plan,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def _snapshot(*files: str, source: str = 'explicit-changed-files') -> ChangeSnapshot:
    return ChangeSnapshot(source, 'head-sha', None, files, 'content-fingerprint')


def _stub_invocations(gate: Gate, step: RecipeStep) -> Iterable[CommandInvocation]:
    count = 2 if step.kind is RecipeStepKind.SCAN_SMOKE else 1
    return tuple(
        CommandInvocation(
            invocation_id=f'{gate.name}:{step.name}:{index}',
            kind=step.kind.value,
            argv=('owner', step.name, str(index)),
            environment=(),
            gate_name=gate.name,
            recipe_step_name=step.name,
        )
        for index in range(count)
    )


def test_full_and_selectors_preserve_catalog_order_and_single_recipe() -> None:
    full = compile_gate_plan(_snapshot(source='full'), mode='full')
    target = compile_gate_plan(_snapshot(source='full'), mode='full', target='java-build')
    gate = compile_gate_plan(_snapshot(source='full'), mode='full', gate='browserBehaviorTests')

    assert full.gates == GATES
    assert len(full.gates) == 20
    assert tuple(item.name for item in target.gates) == (
        'maintenanceLanguagePolicy',
        'javaBuildVerification',
        'javaDuplicationAudit',
    )
    assert gate.gates == (gate_by_name('browserBehaviorTests'),)
    assert target.selector_kind == 'target'
    assert target.selector_value == 'java-build'
    assert gate.selector_kind == 'gate'


def test_empty_incremental_plan_is_representable_but_selector_requires_full() -> None:
    empty = compile_gate_plan(_snapshot())
    assert empty.gates == ()
    assert empty.process_count == 0
    assert len(empty.not_triggered) == 20
    assert {item.reason for item in empty.not_triggered} == {'no-trigger-pattern-matched'}

    with pytest.raises(ValueError, match='use full mode'):
        compile_gate_plan(_snapshot(), gate='browserBehaviorTests')
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


@pytest.mark.parametrize(
    ('path', 'expected_gates', 'expected_patterns', 'expected_process_count'),
    [
        (
            'scripts/gates/planning/plan_compiler.py',
            (
                'scriptToolchainQuality',
                'gateFrameworkTests',
                'repositoryBoundaryAudit',
                'currentVersionPolicy',
                'credentialLeakScan',
                'maintenanceLanguagePolicy',
            ),
            (
                'scripts/**/*.py',
                'scripts/gates/**/*.py',
                'scripts/gates/**',
                'scripts/**',
                'scripts/**',
                'scripts/**/*.py',
            ),
            12,
        ),
        (
            'java/web/src/main/resources/static/js/session.js',
            (
                'currentVersionPolicy',
                'credentialLeakScan',
                'webStaticRules',
                'webResourceContracts',
                'browserVisualTests',
                'browserBehaviorTests',
            ),
            (
                'java/**',
                'java/**',
                'java/web/src/main/resources/**',
                'java/web/src/main/resources/static/**',
                'java/web/src/main/resources/static/**',
                'java/web/src/main/resources/static/**',
            ),
            10,
        ),
        (
            'java/sources/src/main/java/com/feipi/session/browser/source/Adapter.java',
            (
                'currentVersionPolicy',
                'credentialLeakScan',
                'javaBuildVerification',
                'javaDuplicationAudit',
                'scanCommandSmoke',
                'sessionSampleContracts',
            ),
            (
                'java/**',
                'java/**',
                'java/**/src/main/java/**/*.java',
                '**/*.java',
                'java/**/src/main/java/**/*.java',
                'java/sources/**',
                'java/sources/**',
            ),
            7,
        ),
        (
            'java/index-store-sqlite/src/main/java/com/feipi/session/browser/store/IndexStore.java',
            (
                'currentVersionPolicy',
                'credentialLeakScan',
                'javaBuildVerification',
                'javaDuplicationAudit',
                'scanCommandSmoke',
            ),
            (
                'java/**',
                'java/**',
                'java/**/src/main/java/**/*.java',
                '**/*.java',
                'java/**/src/main/java/**/*.java',
                'java/index-store-sqlite/**',
            ),
            6,
        ),
        (
            'tests/playwright/specs/session-detail.spec.js',
            (
                'testSkipProhibition',
                'acceptanceTraceability',
                'testDataPrivacy',
                'credentialLeakScan',
                'webStaticRules',
                'browserVisualTests',
                'browserBehaviorTests',
            ),
            (
                'tests/**/*.js',
                'tests/**/*.js',
                'tests/**',
                'tests/**',
                'tests/**/*.js',
                'tests/playwright/**',
                'tests/playwright/**',
            ),
            11,
        ),
        (
            (
                'java/scan-engine/src/main/java/com/feipi/session/browser/scan/'
                'artifact/ScanArtifact.java'
            ),
            (
                'currentVersionPolicy',
                'credentialLeakScan',
                'javaBuildVerification',
                'javaDuplicationAudit',
                'scanCommandSmoke',
                'sessionSampleContracts',
            ),
            (
                'java/**',
                'java/**',
                'java/**/src/main/java/**/*.java',
                '**/*.java',
                'java/**/src/main/java/**/*.java',
                'java/scan-engine/**',
                'java/scan-engine/src/main/java/com/feipi/session/browser/scan/artifact/**',
            ),
            7,
        ),
    ],
)
def test_representative_path_has_exact_selection_patterns_and_process_count(
    path: str,
    expected_gates: tuple[str, ...],
    expected_patterns: tuple[str, ...],
    expected_process_count: int,
) -> None:
    plan = compile_gate_plan(_snapshot(path), invocation_factory=_stub_invocations)

    assert tuple(gate.name for gate in plan.gates) == expected_gates
    assert tuple(match.pattern for match in plan.matches) == expected_patterns
    assert plan.process_count == expected_process_count


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
