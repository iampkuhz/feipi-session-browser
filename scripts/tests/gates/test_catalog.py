"""Catalog 声明、公共 ID、RecipeStep owner 与 Trigger 契约。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest
from scripts.gates.catalog.gate_contracts import (
    ExecutionMode,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
    TriggerMode,
)
from scripts.gates.catalog.registry import (
    CATALOG,
    GATES,
    TARGET_PRESETS,
    gate_by_name,
    target_preset_by_name,
)
from scripts.gates.catalog.validation import validate_gate_catalog

GATE_IDS = (
    'scriptToolchainQuality',
    'gateFrameworkTests',
    'pythonDependencyAudit',
    'repositoryBoundaryAudit',
    'testSkipProhibition',
    'currentVersionPolicy',
    'acceptanceTraceability',
    'testDataPrivacy',
    'credentialLeakScan',
    'maintenanceLanguagePolicy',
    'agentConfigurationPolicy',
    'governanceLayoutValidation',
    'webStaticRules',
    'webResourceContracts',
    'browserVisualTests',
    'browserBehaviorTests',
    'javaBuildVerification',
    'javaDuplicationAudit',
    'scanCommandSmoke',
    'sessionSampleContracts',
)
TARGET_PRESET_IDS = (
    'gate-infrastructure',
    'agent-governance',
    'web-interface',
    'java-source',
    'java-build',
    'session-pipeline',
)


def _catalog_with_gate(gate):
    gates = tuple(gate if item.name == gate.name else item for item in CATALOG.gates)
    return replace(CATALOG, gates=gates)


def test_catalog_has_exact_public_inventory_and_all_recipe_step_kinds() -> None:
    assert tuple(preset.name for preset in TARGET_PRESETS) == TARGET_PRESET_IDS
    assert tuple(gate.name for gate in GATES) == GATE_IDS
    assert {step.kind for gate in GATES for step in gate.recipe.steps} == set(RecipeStepKind)


def test_each_gate_has_one_recipe_and_two_non_blocking_duration_expectations() -> None:
    validate_gate_catalog(CATALOG)
    for gate in CATALOG.gates:
        assert gate.recipe.steps
        assert len({step.name for step in gate.recipe.steps}) == len(gate.recipe.steps)
        for step in gate.recipe.steps:
            if step.kind is RecipeStepKind.GRADLE_TASK:
                assert len(step.tasks) == 1
            elif step.kind is RecipeStepKind.JAVA_RULE:
                assert len(step.rules) == 1
        for mode in ExecutionMode:
            assert gate.recipe.duration_for(mode) > 0


def test_composite_gate_steps_keep_explicit_owner_names() -> None:
    assert tuple(step.name for step in gate_by_name('scriptToolchainQuality').recipe.steps) == (
        'pythonFormat',
        'pythonLint',
        'bashSyntax',
        'pythonDependencyDeclarations',
        'pythonSourceSecurity',
        'pythonDeadCode',
    )
    assert tuple(step.name for step in gate_by_name('agentConfigurationPolicy').recipe.steps) == (
        'agentEntrypoints',
        'agentDocumentation',
    )
    assert tuple(
        step.check_id for step in gate_by_name('maintenanceLanguagePolicy').recipe.steps
    ) == (
        'repository.maintenance-language',
        'source.code-comment-language',
    )
    web_steps = gate_by_name('webStaticRules').recipe.steps
    assert tuple((step.name, step.kind, step.rules) for step in web_steps) == (
        ('rawInnerhtml', RecipeStepKind.JAVA_RULE, ('raw-innerhtml',)),
        ('layoutInlineStyle', RecipeStepKind.JAVA_RULE, ('layout-inline-style',)),
        ('templateContract', RecipeStepKind.JAVA_RULE, ('template-contract',)),
        ('staticCssContract', RecipeStepKind.JAVA_RULE, ('static-resource-contract',)),
        ('cssOwnership', RecipeStepKind.JAVA_RULE, ('css-ownership',)),
    )


def test_repaired_triggers_use_current_paths_and_exclude_unrelated_gate_core() -> None:
    scan_paths = gate_by_name('scanCommandSmoke').trigger.paths
    sample_paths = gate_by_name('sessionSampleContracts').trigger.paths
    agent_paths = gate_by_name('agentConfigurationPolicy').trigger.paths
    web_paths = gate_by_name('webStaticRules').trigger.paths

    assert 'java/index-store-sqlite/**' in scan_paths
    assert 'java/index-sqlite/**' not in scan_paths
    assert (
        'java/scan-engine/src/main/java/com/feipi/session/browser/scan/artifact/**' in sample_paths
    )
    assert 'java/artifact-normalized/**' not in sample_paths
    assert 'scripts/gates/**/*.py' not in agent_paths
    assert all('scripts/gates/execution/' not in pattern for pattern in web_paths)


def test_java_build_verification_runs_complete_root_check() -> None:
    step = gate_by_name('javaBuildVerification').recipe.steps[0]
    assert step.tasks == ('check',)
    assert step.args == ('--parallel', '--build-cache')
    assert '-x' not in step.args


def test_lookup_is_strict_frozen_and_has_no_old_aliases() -> None:
    assert target_preset_by_name('java-source').description.startswith('人工运行')
    with pytest.raises(ValueError, match='unknown Gate'):
        gate_by_name('missing')
    with pytest.raises(ValueError, match='unknown TargetPreset'):
        target_preset_by_name('missing')
    with pytest.raises(FrozenInstanceError):
        CATALOG.gates = ()  # type: ignore[misc]


def test_duplicate_unknown_and_unused_target_presets_fail_closed() -> None:
    duplicate = replace(
        CATALOG, target_presets=(*CATALOG.target_presets, CATALOG.target_presets[0])
    )
    with pytest.raises(ValueError, match='must not contain duplicates'):
        validate_gate_catalog(duplicate)

    gate = replace(CATALOG.gates[0], target_presets=('missing-target',))
    with pytest.raises(ValueError, match='unknown TargetPresets'):
        validate_gate_catalog(_catalog_with_gate(gate))

    unused = replace(CATALOG.target_presets[0], name='unused')
    with pytest.raises(ValueError, match='selects no Gate'):
        validate_gate_catalog(replace(CATALOG, target_presets=(*CATALOG.target_presets, unused)))


def test_trigger_description_path_and_duration_invariants_fail_closed() -> None:
    source = CATALOG.gates[0]
    mutations = (
        (replace(source, description='not Chinese.'), 'Chinese sentence'),
        (
            replace(source, trigger=GateTrigger(TriggerMode.ALWAYS, ('scripts/**',))),
            'cannot contain',
        ),
        (replace(source, trigger=GateTrigger(TriggerMode.CHANGED)), 'requires paths'),
        (
            replace(source, trigger=GateTrigger(TriggerMode.CHANGED, ('../outside',))),
            'invalid repository',
        ),
        (
            replace(
                source,
                recipe=replace(
                    source.recipe,
                    duration_expectations=replace(
                        source.recipe.duration_expectations,
                        incremental=0,
                    ),
                ),
            ),
            'positive integer',
        ),
    )
    for gate, message in mutations:
        with pytest.raises(ValueError, match=message):
            validate_gate_catalog(_catalog_with_gate(gate))


def test_recipe_step_names_and_owner_fields_fail_closed() -> None:
    source = gate_by_name('scriptToolchainQuality')
    duplicate_steps = (source.recipe.steps[0], source.recipe.steps[0])
    with pytest.raises(ValueError, match='must not contain duplicates'):
        validate_gate_catalog(
            _catalog_with_gate(
                replace(source, recipe=replace(source.recipe, steps=duplicate_steps))
            )
        )

    reuse = gate_by_name('javaDuplicationAudit')
    bad_task = replace(reuse.recipe.steps[0], tasks=('reuseStandardCpd', 'check'))
    with pytest.raises(ValueError, match='exactly one item'):
        validate_gate_catalog(
            _catalog_with_gate(replace(reuse, recipe=replace(reuse.recipe, steps=(bad_task,))))
        )

    web = gate_by_name('webStaticRules')
    duplicate_rule = RecipeStep(
        'duplicateRule',
        RecipeStepKind.JAVA_RULE,
        rules=web.recipe.steps[0].rules,
    )
    with pytest.raises(ValueError, match='duplicate Java rule ownership'):
        validate_gate_catalog(
            _catalog_with_gate(
                replace(web, recipe=replace(web.recipe, steps=(*web.recipe.steps, duplicate_rule)))
            )
        )
