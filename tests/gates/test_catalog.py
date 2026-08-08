"""Typed Python Gate Catalog 的声明、引用与 recipe 契约。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from scripts.gates.catalog import (
    CATALOG,
    gate_by_name,
    target_by_name,
    validate_catalog_schema,
)
from scripts.gates.model import ExecutionMode, GateTrigger, RunKind, RunStep, TriggerMode
from scripts.gates.planner import pattern_matches

REMOVED_GATES = {
    'pythonFormat',
    'pythonLint',
    'bashSyntax',
    'pythonDependencyDeclarations',
    'pythonSourceSecurity',
    'pythonDeadCode',
    'agentEntryParity',
    'agentPermissionPolicy',
    'protectedRootsSync',
    'subagentHandoffProtocol',
    'agentPolicySize',
    'scriptCommentLanguage',
    'skillRegistry',
    'harnessStructure',
    'openspecLayout',
    'rawInnerhtml',
    'layoutInlineStyle',
    'templateContract',
    'staticCssContract',
    'cssOwnership',
    'javaChineseComments',
    'javaRecordComponentJavadocs',
    'noJavaSuppressWarnings',
    'reuseStandardCpd',
    'reuseAnalyzeIncremental',
    'javaSourcePolicy',
    'noJavaTestSkips',
    'doctor',
}

COMPOSITE_LEAF_NAMES = {
    'scriptSourceStandard': (
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    ),
    'agentPolicy': (
        'agentRuntimePolicy',
        'agentDocumentPolicy',
    ),
    'languagePolicy': ('languagePolicy', 'scriptCommentLanguage'),
    'governanceStructure': ('skillRegistry', 'harnessStructure', 'openspecLayout'),
    'webSourcePolicy': (
        'rawInnerhtml',
        'layoutInlineStyle',
        'templateContract',
        'staticCssContract',
        'cssOwnership',
    ),
}


def _catalog_with_gate(gate):
    gates = tuple(gate if item.name == gate.name else item for item in CATALOG.gates)
    return replace(CATALOG, gates=gates)


def test_current_catalog_has_stable_inventory_and_all_six_run_kinds() -> None:
    assert tuple(target.name for target in CATALOG.targets) == (
        'python-standard',
        'harness',
        'session-detail',
        'java-src',
        'java-build',
        'scan-script-smoke',
    )
    assert len(CATALOG.gates) == 20
    assert tuple(gate.name for gate in CATALOG.gates[:3]) == (
        'scriptSourceStandard',
        'pythonHarnessTests',
        'pythonDependencyVulnerabilities',
    )
    assert tuple(gate.name for gate in CATALOG.gates[-3:]) == (
        'javaReusePolicy',
        'scanScriptSmoke',
        'sessionSamples',
    )
    assert {step.kind for gate in CATALOG.gates for step in gate.run.steps} == set(RunKind)


def test_every_gate_has_one_recipe_and_two_non_blocking_targets() -> None:
    validate_catalog_schema(CATALOG)
    for gate in CATALOG.gates:
        assert gate.name and gate.description
        assert gate.run.steps
        assert len({step.name for step in gate.run.steps}) == len(gate.run.steps)
        for step in gate.run.steps:
            if step.kind is RunKind.GRADLE_TASK:
                assert len(step.tasks) == 1
            elif step.kind is RunKind.JAVA_RULE:
                assert len(step.rules) == 1
        for mode in ExecutionMode:
            assert gate.run.target_for(mode) > 0


def test_standard_source_gate_owns_all_stable_external_tool_checks() -> None:
    run = gate_by_name('scriptSourceStandard').run
    assert tuple(step.name for step in run.steps) == COMPOSITE_LEAF_NAMES['scriptSourceStandard']
    assert run.target_for('incremental') == 80
    assert run.target_for('full') == 165
    assert not hasattr(run, 'incremental')
    assert not hasattr(run, 'full')


def test_all_merged_gates_keep_explicit_leaf_owners() -> None:
    for gate_name, leaf_names in COMPOSITE_LEAF_NAMES.items():
        assert tuple(step.name for step in gate_by_name(gate_name).run.steps) == leaf_names

    web_steps = gate_by_name('webSourcePolicy').run.steps
    assert tuple((step.name, step.kind, step.rules) for step in web_steps) == (
        ('rawInnerhtml', RunKind.JAVA_RULE, ('raw-innerhtml',)),
        ('layoutInlineStyle', RunKind.JAVA_RULE, ('layout-inline-style',)),
        ('templateContract', RunKind.JAVA_RULE, ('template-contract',)),
        ('staticCssContract', RunKind.JAVA_RULE, ('static-resource-contract',)),
        ('cssOwnership', RunKind.JAVA_RULE, ('css-ownership',)),
    )
    assert tuple(
        (step.name, step.kind, step.tasks) for step in gate_by_name('javaReusePolicy').run.steps
    ) == (('reuseStandardCpd', RunKind.GRADLE_TASK, ('reuseStandardCpd',)),)


@pytest.mark.parametrize(
    ('gate_name', 'representative_paths'),
    [
        (
            'scriptSourceStandard',
            ('pyproject.toml', 'scripts/gates/cli.py', 'tests/gates/test_cli.py', 'scripts/run.sh'),
        ),
        (
            'agentPolicy',
            (
                'AGENTS.md',
                '.claude/commands/diagnose-ui-gate.md',
                'skills/authoring/example/SKILL.md',
                'harness/agent-policy.manifest.yaml',
                'scripts/gates/checks/agent/check_agent_document_policy.py',
            ),
        ),
        (
            'languagePolicy',
            (
                'CLAUDE.md',
                'openspec/changes/example/proposal.md',
                'scripts/gates/checks/source/check_language_policy.py',
                'config/technical-terms.json',
            ),
        ),
        (
            'governanceStructure',
            (
                'harness/skill-registry.yaml',
                'skills/authoring/example/SKILL.md',
                'scripts/gates/checks/agent/check_skill_registry.py',
                'openspec/changes/example/proposal.md',
            ),
        ),
        (
            'webSourcePolicy',
            (
                'java/web/src/main/resources/static/js/session/detail.js',
                'java/web/src/main/resources/templates/session/detail.html',
                'java/tests/quality-gates/build.gradle.kts',
                'config/web-quality-baselines.json',
                'tests/playwright/session-detail.spec.js',
            ),
        ),
        (
            'javaCheck',
            (
                'java/core/src/main/java/example/Session.java',
                'java/core/src/test/kotlin/example/SessionTest.kt',
                'gradle/build-logic/src/main/kotlin/example/plugin.gradle.kts',
                'build.gradle.kts',
            ),
        ),
        (
            'javaReusePolicy',
            (
                'java/core/src/main/java/example/Session.java',
                'config/reuse-policy/policy.json',
                'java/web/build.gradle.kts',
            ),
        ),
    ],
)
def test_merged_gate_triggers_cover_each_maintenance_boundary(
    gate_name: str, representative_paths: tuple[str, ...]
) -> None:
    patterns = gate_by_name(gate_name).trigger.paths
    for path in representative_paths:
        assert any(pattern_matches(path, pattern) for pattern in patterns), (gate_name, path)


def test_lookup_and_models_are_strict_and_frozen() -> None:
    assert target_by_name('java-src').description.startswith('人工运行')
    with pytest.raises(ValueError, match='Unknown quality gate'):
        gate_by_name('missing')
    with pytest.raises(ValueError, match='Unknown quality target'):
        target_by_name('missing')
    for name in REMOVED_GATES:
        with pytest.raises(ValueError, match='Unknown quality gate'):
            gate_by_name(name)
    with pytest.raises(FrozenInstanceError):
        CATALOG.gates = ()  # type: ignore[misc]


def test_duplicate_unknown_and_unused_targets_fail_closed() -> None:
    duplicate = replace(CATALOG, targets=(*CATALOG.targets, CATALOG.targets[0]))
    with pytest.raises(ValueError, match='must not contain duplicates'):
        validate_catalog_schema(duplicate)

    gate = replace(CATALOG.gates[0], targets=('missing-target',))
    with pytest.raises(ValueError, match='unknown Targets'):
        validate_catalog_schema(_catalog_with_gate(gate))

    unused = replace(CATALOG.targets[0], name='unused')
    with pytest.raises(ValueError, match='selects no Gate'):
        validate_catalog_schema(replace(CATALOG, targets=(*CATALOG.targets, unused)))


def test_trigger_description_path_and_timing_invariants_fail_closed() -> None:
    source = CATALOG.gates[0]
    mutations = (
        (replace(source, description='not Chinese.'), 'Chinese sentence'),
        (
            replace(source, trigger=GateTrigger(TriggerMode.ALWAYS, ('scripts/**',))),
            'cannot contain paths',
        ),
        (replace(source, trigger=GateTrigger(TriggerMode.CHANGED)), 'requires paths'),
        (
            replace(source, trigger=GateTrigger(TriggerMode.CHANGED, ('../outside',))),
            'invalid repository path',
        ),
        (
            replace(
                source,
                run=replace(
                    source.run,
                    target_seconds=replace(source.run.target_seconds, incremental=0),
                ),
            ),
            'positive integer',
        ),
    )
    for gate, message in mutations:
        with pytest.raises(ValueError, match=message):
            validate_catalog_schema(_catalog_with_gate(gate))


def test_leaf_names_and_owner_fields_fail_closed() -> None:
    source = gate_by_name('scriptSourceStandard')
    duplicate_steps = (source.run.steps[0], source.run.steps[0])
    with pytest.raises(ValueError, match='must not contain duplicates'):
        validate_catalog_schema(
            _catalog_with_gate(replace(source, run=replace(source.run, steps=duplicate_steps)))
        )

    reuse = gate_by_name('javaReusePolicy')
    bad_task = replace(reuse.run.steps[0], tasks=('reuseStandardCpd', 'check'))
    with pytest.raises(ValueError, match='exactly one item'):
        validate_catalog_schema(
            _catalog_with_gate(
                replace(reuse, run=replace(reuse.run, steps=(bad_task, *reuse.run.steps[1:])))
            )
        )

    web = gate_by_name('webSourcePolicy')
    bad_rule = replace(web.run.steps[0], rules=('raw-innerhtml', 'other'))
    with pytest.raises(ValueError, match='exactly one item'):
        validate_catalog_schema(
            _catalog_with_gate(
                replace(web, run=replace(web.run, steps=(bad_rule, *web.run.steps[1:])))
            )
        )

    command_with_rule = replace(source.run.steps[0], rules=('hidden-owner',))
    with pytest.raises(ValueError, match='fields unused'):
        validate_catalog_schema(
            _catalog_with_gate(
                replace(
                    source,
                    run=replace(source.run, steps=(command_with_rule, *source.run.steps[1:])),
                )
            )
        )


def test_duplicate_java_rule_owner_is_rejected() -> None:
    source = gate_by_name('webSourcePolicy')
    duplicate = replace(
        source,
        run=replace(
            source.run,
            steps=(
                *source.run.steps,
                RunStep('duplicateRule', RunKind.JAVA_RULE, rules=(source.run.steps[0].rules[0],)),
            ),
        ),
    )
    with pytest.raises(ValueError, match='duplicate Java rule ownership'):
        validate_catalog_schema(_catalog_with_gate(duplicate))
