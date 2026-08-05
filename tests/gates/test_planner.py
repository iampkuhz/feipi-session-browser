"""Gate-first Trigger 与 mode×selector 规划契约。"""

from dataclasses import replace

import pytest
from scripts.gates.catalog import CATALOG, gate_by_name
from scripts.gates.model import ExecutionMode, GateTrigger, TriggerMode
from scripts.gates.planner import (
    classify_path,
    gate_matches,
    gates_for_target,
    normalize_repo_path,
    pattern_matches,
    plan,
)


@pytest.mark.parametrize(
    ('path', 'pattern', 'matched'),
    [
        ('scripts/gates/planner.py', 'scripts/**/*.py', True),
        ('scripts/planner.py', 'scripts/**/*.py', True),
        ('tests/playwright/specs/detail.spec.ts', 'tests/**/*.ts', True),
        ('tests/playwright/specs/detail.spec.js', 'tests/**/*.ts', False),
        (r'java\web\src\main\A.java', 'java/**/src/main/**/*.java', True),
        ('README.md', '*.md', True),
        ('docs/README.md', '*.md', False),
    ],
)
def test_glob_semantics_are_cross_platform_and_stable(
    path: str, pattern: str, matched: bool
) -> None:
    assert pattern_matches(path, pattern) is matched


def test_path_classification_is_governance_only_and_first_match_wins() -> None:
    classification = classify_path(r'java\core-domain\src\main\java\com\feipi\Foo.java')
    assert classification.file == 'java/core-domain/src/main/java/com/feipi/Foo.java'
    assert classification.category == 'java-src'
    assert classification.allowed is True
    assert not hasattr(classification, 'targets')
    assert classify_path('some/random/Foo.java').allowed is False


def test_incremental_auto_selection_matches_each_gate_trigger_directly() -> None:
    files = ('tests/playwright/specs/detail.spec.ts',)
    result = plan(files)
    expected = tuple(gate for gate in CATALOG.gates if gate_matches(gate, files))
    assert result.mode is ExecutionMode.INCREMENTAL
    assert result.gates == expected
    names = {gate.name for gate in result.gates}
    assert {'browserLayout', 'browserInteraction', 'acceptanceCaseMapping'} <= names
    assert 'javaCheck' not in names


def test_always_trigger_is_selected_even_without_changed_files() -> None:
    source = gate_by_name('pythonFormat')
    always = replace(source, trigger=GateTrigger(TriggerMode.ALWAYS))
    assert gate_matches(always, ()) is True
    assert gate_matches(source, ()) is False


def test_full_without_selector_selects_all_41_gates_in_catalog_order() -> None:
    result = plan(mode='full')
    assert result.gates == CATALOG.gates
    assert len(result.gates) == 41
    assert result.changed_files == ()


def test_target_selector_bypasses_trigger_and_keeps_same_members_across_modes() -> None:
    incremental = plan((), target='java-build', mode='incremental')
    full = plan(target='java-build', mode='full')
    assert incremental.gates == full.gates == gates_for_target('java-build')
    assert tuple(gate.name for gate in full.gates) == (
        'scriptCommentLanguage',
        'javaCheck',
        'javaChineseComments',
        'reuseStandardCpd',
        'reuseAnalyzeIncremental',
        'javaApiSnapshot',
    )
    assert incremental.selector == full.selector == 'target'
    assert incremental.selector_value == full.selector_value == 'java-build'


def test_gate_selector_bypasses_trigger_and_mode_only_selects_profile() -> None:
    incremental = plan((), gate='browserInteraction', mode='incremental')
    full = plan(gate='browserInteraction', mode='full')
    assert incremental.gates == full.gates == (gate_by_name('browserInteraction'),)
    assert (
        incremental.gates[0].run.profile_for(incremental.mode)
        is incremental.gates[0].run.incremental
    )
    assert full.gates[0].run.profile_for(full.mode) is full.gates[0].run.full


def test_planner_does_not_use_timing_to_select_gates() -> None:
    gate = gate_by_name('pythonFormat')
    slower = replace(
        gate,
        run=replace(
            gate.run,
            incremental=replace(gate.run.incremental, target_seconds=999_999),
        ),
    )
    assert gate_matches(gate, ('scripts/a.py',)) == gate_matches(slower, ('scripts/a.py',))


@pytest.mark.parametrize(
    ('kwargs', 'message'),
    [
        ({'target': 'missing'}, 'Unknown quality target'),
        ({'gate': 'missing'}, 'Unknown quality gate'),
        ({'target': 'java-src', 'gate': 'javaCheck'}, 'mutually exclusive'),
        ({'mode': 'full', 'changed_files': ('README.md',)}, 'does not accept'),
        ({'mode': 'quick'}, 'quick'),
    ],
)
def test_invalid_mode_selector_matrix_fails_closed(kwargs: dict[str, object], message: str) -> None:
    changed_files = kwargs.pop('changed_files', ())
    with pytest.raises(ValueError, match=message):
        plan(changed_files, **kwargs)  # type: ignore[arg-type]


def test_path_normalization_does_not_change_gate_order() -> None:
    unix = plan(('scripts/gates/planner.py',))
    windows = plan((r'.\scripts\gates\planner.py',))
    assert normalize_repo_path(r'.\scripts\gates\planner.py') == 'scripts/gates/planner.py'
    assert unix.gates == windows.gates
