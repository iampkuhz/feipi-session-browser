"""Typed Gate catalog 的 schema、tier 与唯一性 contract。"""

from dataclasses import FrozenInstanceError

import pytest
from scripts.gates.catalog import CATALOG, GATES, gate_by_name, tier_by_name
from scripts.gates.planner import gates_for_tier, validate_catalog


def test_catalog_schema_is_complete_unique_and_acyclic() -> None:
    validate_catalog()
    assert len(GATES) == 45
    assert len({gate.name for gate in GATES}) == 45
    for gate in GATES:
        assert gate.targets
        assert gate.executor_type
        assert bool(gate.command) != bool(gate.gradle_tasks)
        assert isinstance(gate.java_rules, tuple)
        assert gate.timeout_seconds > 0
        assert gate.incremental_mode
        assert gate.changed_files_input
        assert isinstance(gate.included_by, tuple)
        assert 'full' in gate.tiers
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
        'noJavaSuppressWarnings',
        'reuseStandardCpd',
    }


def test_java_quality_rules_share_one_declarative_gradle_entrypoint() -> None:
    expected = {
        'javaChineseComments': ('java-comment-language',),
        'javaRecordComponentJavadocs': ('record-component-javadocs',),
        'noJavaSuppressWarnings': ('no-pmd-suppressions',),
        'javaApiSnapshot': ('java-api-snapshot',),
        'templateContract': ('template-contract',),
        'staticCssContract': ('static-resource-contract',),
        'rawInnerhtml': ('raw-innerhtml',),
        'layoutInlineStyle': ('layout-inline-style',),
    }

    for gate_name, rules in expected.items():
        gate = gate_by_name(gate_name)
        assert gate.gradle_tasks == (':java:tests:quality-gates:runJavaQualityGates',)
        assert gate.java_rules == rules

    with pytest.raises(ValueError, match='Unknown quality gate'):
        gate_by_name('javaModuleBoundaries')


def test_template_contract_has_one_java_owner_and_fixed_resource_root() -> None:
    gate = gate_by_name('templateContract')
    target_rules = {rule.target: rule for rule in gate.target_rules}

    assert gate.command is None
    assert gate.gradle_tasks == (':java:tests:quality-gates:runJavaQualityGates',)
    assert gate.java_rules == ('template-contract',)
    assert target_rules['session-detail'].patterns == ('java/web/src/main/resources/templates/**',)
    assert target_rules['java-src'].patterns == (
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRule.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/TemplateContractRuleTest.java',
    )


def test_static_contract_has_one_java_owner_and_complete_resource_inputs() -> None:
    gate = gate_by_name('staticCssContract')
    target_rules = {rule.target: rule for rule in gate.target_rules}

    assert gate.command is None
    assert gate.gradle_tasks == (':java:tests:quality-gates:runJavaQualityGates',)
    assert gate.java_rules == ('static-resource-contract',)
    assert target_rules['session-detail'].patterns == (
        'java/web/src/main/resources/static/**/*.css',
        'java/web/src/main/resources/static/**/*.js',
        'java/web/src/main/resources/templates/**/*.html',
        'config/web-quality-baselines.json',
        'tests/ui/test_web_static_contract.py',
    )
    assert target_rules['java-src'].patterns == (
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/StaticResourceContractRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/WebQualityBaseline.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/StaticResourceContractRuleTest.java',
    )


def test_raw_and_layout_contracts_have_independent_java_owners_and_complete_inputs() -> None:
    raw = gate_by_name('rawInnerhtml')
    layout = gate_by_name('layoutInlineStyle')
    raw_targets = {rule.target: rule for rule in raw.target_rules}
    layout_targets = {rule.target: rule for rule in layout.target_rules}

    assert raw.command is None
    assert raw.gradle_tasks == (':java:tests:quality-gates:runJavaQualityGates',)
    assert raw.java_rules == ('raw-innerhtml',)
    assert raw_targets['session-detail'].patterns == (
        'java/web/src/main/resources/static/js/**/*.js',
        'config/web-quality-baselines.json',
    )
    assert raw_targets['acceptance-contracts'].patterns == ('tests/**/*.js',)
    assert raw_targets['python-standard'].patterns == ('scripts/**/*.js',)
    assert raw_targets['java-src'].patterns == (
        'java/tests/quality-gates/build.gradle.kts',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/BaselineUpdatableRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualityRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualitySummary.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/RepositorySourceSet.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/cli/QualityGateCli.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/cli/BaselineUpdateWriter.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/PythonTextSemantics.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/WebQualityBaseline.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/RawInnerHtmlRule.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/core/QualityViolationTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/core/RepositorySourceSetTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/RawInnerHtmlRuleTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/cli/WebBaselineUpdateCliTest.java',
    )

    assert layout.command is None
    assert layout.gradle_tasks == (':java:tests:quality-gates:runJavaQualityGates',)
    assert layout.java_rules == ('layout-inline-style',)
    assert layout_targets['session-detail'].patterns == (
        'java/web/src/main/resources/static/js/**/*.js',
        'java/web/src/main/resources/templates/**/*.html',
        'config/web-quality-baselines.json',
    )
    assert layout_targets['java-src'].patterns == (
        'java/tests/quality-gates/build.gradle.kts',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/BaselineUpdatableRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualityRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualitySummary.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/RepositorySourceSet.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/cli/QualityGateCli.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/cli/BaselineUpdateWriter.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/PythonTextSemantics.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/WebQualityBaseline.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/LayoutInlineStyleRule.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/core/QualityViolationTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/core/RepositorySourceSetTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/LayoutInlineStyleRuleTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/cli/WebBaselineUpdateCliTest.java',
    )


def test_script_comment_gate_scans_only_real_script_sources() -> None:
    gate = gate_by_name('scriptCommentLanguage')
    target_rules = {rule.target: rule for rule in gate.target_rules}

    assert gate.targets == ('python-standard', 'java-build')
    assert target_rules['python-standard'].patterns == ('scripts/**/*.py', 'scripts/**/*.sh')
    assert target_rules['java-build'].patterns == ('config/technical-terms.json',)
    assert gate.command is not None
    assert gate.command.argv == (
        '{python}',
        '-m',
        'scripts.checks',
        'source.comment-language',
        'scripts',
    )


def test_java_test_outcomes_use_existing_gradle_owner() -> None:
    gate = gate_by_name('noJavaTestSkips')

    assert gate.command is None
    assert gate.gradle_tasks == ('verifyNoSkippedJavaTests',)


def test_session_samples_uses_existing_gradle_owner() -> None:
    gate = gate_by_name('sessionSamples')

    assert gate.command is None
    assert gate.gradle_tasks == (':java:tests:contracts:sampleIntegrationTest',)


def test_reuse_standard_cpd_uses_gradle_owner_and_changed_files_environment() -> None:
    gate = gate_by_name('reuseStandardCpd')

    assert gate.command is None
    assert gate.gradle_tasks == ('reuseStandardCpd',)
    assert gate.changed_files_input.value == 'environment'
