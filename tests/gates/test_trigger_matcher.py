"""TriggerMatcher pattern and causal-evidence contracts."""

from __future__ import annotations

from scripts.gates.catalog.gate_contracts import (
    DurationExpectations,
    Gate,
    GateRecipe,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
    TriggerMode,
)
from scripts.gates.planning.trigger_matcher import match_trigger, trigger_pattern_matches


def _gate(name: str, mode: TriggerMode, *patterns: str) -> Gate:
    return Gate(
        name=name,
        description=f'{name} description',
        trigger=GateTrigger(mode, patterns),
        target_presets=(),
        recipe=GateRecipe(
            DurationExpectations(1, 1),
            (RecipeStep('owner', RecipeStepKind.COMMAND, argv=('true',)),),
        ),
    )


def test_glob_semantics_are_cross_platform_and_stable() -> None:
    assert trigger_pattern_matches(r'.\scripts\gates\planning\a.py', 'scripts/**/*.py')
    assert trigger_pattern_matches('scripts/a.py', 'scripts/**/*.py')
    assert trigger_pattern_matches('tests/specs/detail.spec.ts', 'tests/**/*.ts')
    assert not trigger_pattern_matches('tests/specs/detail.spec.js', 'tests/**/*.ts')
    assert trigger_pattern_matches('README.md', '*.md')
    assert not trigger_pattern_matches('docs/README.md', '*.md')


def test_match_trigger_preserves_every_file_pattern_gate_reason() -> None:
    gates = (
        _gate('python', TriggerMode.CHANGED, 'scripts/**/*.py', 'scripts/gates/**'),
        _gate('always', TriggerMode.ALWAYS),
        _gate('java', TriggerMode.CHANGED, 'java/**/*.java'),
    )

    matches = match_trigger(('scripts/gates/planning/a.py', 'README.md'), gates)

    assert tuple((item.file, item.pattern, item.gate_name) for item in matches) == (
        ('scripts/gates/planning/a.py', 'scripts/**/*.py', 'python'),
        ('scripts/gates/planning/a.py', 'scripts/gates/**', 'python'),
        ('<always>', '<always>', 'always'),
    )


def test_match_trigger_returns_no_reason_for_unmatched_changed_gate() -> None:
    gate = _gate('java', TriggerMode.CHANGED, 'java/**/*.java')
    assert match_trigger(('README.md',), (gate,)) == ()
