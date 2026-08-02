"""Typed Gate catalog 的 schema、分片加载、tier 与唯一性 contract。"""

import hashlib
import json
import shutil
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path

import pytest
import yaml
from scripts.gates.catalog import CATALOG, GATES, _load_catalog, gate_by_name, tier_by_name
from scripts.gates.planner import gates_for_tier, validate_catalog

GATE_FILES = (
    'gates/python-tooling.yaml',
    'gates/repository-safety.yaml',
    'gates/harness-governance.yaml',
    'gates/web-quality.yaml',
    'gates/java-quality.yaml',
    'gates/product-smoke.yaml',
)
GATE_NAMES = (
    'pythonFormat',
    'pythonLint',
    'pythonCoverage',
    'pythonAudit',
    'pythonComplexity',
    'pythonDeadCode',
    'pythonDeps',
    'ignoredTrackedFiles',
    'misplacedGeneratedPaths',
    'bashSyntax',
    'scriptCommentLanguage',
    'pythonCompile',
    'noTestSkips',
    'languagePolicy',
    'protectedRootsSync',
    'subagentHandoffProtocol',
    'pytest',
    'doctor',
    'repoStructure',
    'repoSlimming',
    'rawInnerhtml',
    'layoutInlineStyle',
    'acceptanceContracts',
    'agentPolicySize',
    'skillRegistry',
    'noRealSessionFixtures',
    'secretLikeContent',
    'harnessStructure',
    'openspecLayout',
    'templateContract',
    'staticCssContract',
    'cssOwnership',
    'browserLayout',
    'browserInteraction',
    'indexIntegrity',
    'javaCheck',
    'javaChineseComments',
    'javaRecordComponentJavadocs',
    'noJavaTestSkips',
    'noJavaSuppressWarnings',
    'reuseStandardCpd',
    'reuseAnalyzeIncremental',
    'javaApiSnapshot',
    'scanScriptSmoke',
    'sessionSamples',
)


@pytest.fixture
def catalog_tree(tmp_path: Path) -> Path:
    """复制真实声明，供 fail-closed 测试只修改隔离目录。"""
    source = Path(__file__).resolve().parents[2] / 'config'
    shutil.copy2(source / 'gates.yaml', tmp_path / 'gates.yaml')
    shutil.copytree(source / 'gates', tmp_path / 'gates')
    return tmp_path / 'gates.yaml'


def _read_yaml(path: Path) -> dict[str, object]:
    """读取测试目录中的 YAML mapping。"""
    result = yaml.safe_load(path.read_text(encoding='utf-8'))
    assert isinstance(result, dict)
    return result


def _write_yaml(path: Path, data: object) -> None:
    """稳定写回测试 YAML，不影响被测 loader。"""
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')


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


def test_fragmented_catalog_preserves_exact_typed_inventory() -> None:
    assert tuple(gate.name for gate in CATALOG.gates) == GATE_NAMES
    normalized = json.dumps(
        asdict(CATALOG), ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode()
    assert hashlib.sha256(normalized).hexdigest() == (
        '44a3d5063ce3cf64356ffa61e491415a83d3e968921b1b52e75a6be2fb60ea1d'
    )


def test_root_index_has_exact_schema_and_ordered_business_fragments(catalog_tree: Path) -> None:
    root = _read_yaml(catalog_tree)
    assert set(root) == {
        'version',
        'targets',
        'gate_files',
        'path_rules',
        'scan_script_smoke_patterns',
        'tiers',
    }
    assert root['version'] == 'gate-catalog:v5'
    assert tuple(root['gate_files']) == GATE_FILES  # type: ignore[arg-type]
    assert _load_catalog(catalog_tree) == CATALOG


@pytest.mark.parametrize(
    'gate_files',
    [
        [],
        [*GATE_FILES, GATE_FILES[-1]],
        ['/tmp/python-tooling.yaml', *GATE_FILES[1:]],
        ['gates\\python-tooling.yaml', *GATE_FILES[1:]],
        ['gates/./python-tooling.yaml', *GATE_FILES[1:]],
        ['gates/../python-tooling.yaml', *GATE_FILES[1:]],
        ['gates/nested/python-tooling.yaml', *GATE_FILES[1:]],
        ['gates/python_tooling.yaml', *GATE_FILES[1:]],
        ['gates/python-tooling.yml', *GATE_FILES[1:]],
    ],
)
def test_root_rejects_empty_duplicate_or_noncanonical_includes(
    catalog_tree: Path, gate_files: list[str]
) -> None:
    root = _read_yaml(catalog_tree)
    root['gate_files'] = gate_files
    _write_yaml(catalog_tree, root)

    with pytest.raises(ValueError):
        _load_catalog(catalog_tree)


def test_root_rejects_inline_gates_unknown_keys_and_duplicate_yaml_keys(
    catalog_tree: Path,
) -> None:
    root = _read_yaml(catalog_tree)
    root['gates'] = []
    _write_yaml(catalog_tree, root)
    with pytest.raises(ValueError, match='catalog keys are invalid'):
        _load_catalog(catalog_tree)

    root.pop('gates')
    _write_yaml(catalog_tree, root)
    with catalog_tree.open('a', encoding='utf-8') as stream:
        stream.write('\nversion: duplicate\n')
    with pytest.raises(ValueError, match='duplicate YAML mapping key'):
        _load_catalog(catalog_tree)


def test_loader_rejects_yaml_anchor_or_alias(catalog_tree: Path) -> None:
    source = catalog_tree.read_text(encoding='utf-8')
    catalog_tree.write_text(source.replace('targets:', 'targets: &targets', 1), encoding='utf-8')

    with pytest.raises(ValueError, match='anchors and aliases'):
        _load_catalog(catalog_tree)


def test_fragment_must_have_only_one_gates_key(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read_yaml(fragment)
    data['metadata'] = {}
    _write_yaml(fragment, data)

    with pytest.raises(ValueError, match=r'gate fragment.*keys are invalid'):
        _load_catalog(catalog_tree)


def test_fragment_gates_must_not_be_empty(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    _write_yaml(fragment, {'gates': []})

    with pytest.raises(ValueError, match='gates must not be empty'):
        _load_catalog(catalog_tree)


def test_fragment_rejects_duplicate_yaml_key(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    with fragment.open('a', encoding='utf-8') as stream:
        stream.write('\ngates: []\n')

    with pytest.raises(ValueError, match='duplicate YAML mapping key'):
        _load_catalog(catalog_tree)


def test_fragment_rejects_duplicate_gate_with_both_file_locations(catalog_tree: Path) -> None:
    first_path = catalog_tree.parent / GATE_FILES[0]
    second_path = catalog_tree.parent / GATE_FILES[1]
    first = _read_yaml(first_path)
    second = _read_yaml(second_path)
    second['gates'].append(first['gates'][0])  # type: ignore[union-attr,index]
    _write_yaml(second_path, second)

    with pytest.raises(
        ValueError,
        match=r'duplicate Gate name.*repository-safety\.yaml.*python-tooling\.yaml',
    ):
        _load_catalog(catalog_tree)


@pytest.mark.parametrize('value', [None, True, '1', -1])
def test_fragment_rejects_missing_or_invalid_catalog_order(
    catalog_tree: Path, value: object
) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read_yaml(fragment)
    gate = data['gates'][0]  # type: ignore[index]
    if value is None:
        gate.pop('catalog_order')
    else:
        gate['catalog_order'] = value
    _write_yaml(fragment, data)

    with pytest.raises(ValueError, match='catalog_order'):
        _load_catalog(catalog_tree)


def test_fragment_rejects_duplicate_catalog_order(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[0]
    data = _read_yaml(fragment)
    gates = data['gates']  # type: ignore[assignment]
    gates[1]['catalog_order'] = gates[0]['catalog_order']
    _write_yaml(fragment, data)
    with pytest.raises(ValueError, match='duplicate Gate catalog_order'):
        _load_catalog(catalog_tree)


def test_fragment_declaration_order_does_not_change_catalog_order(catalog_tree: Path) -> None:
    for name in GATE_FILES:
        fragment = catalog_tree.parent / name
        data = _read_yaml(fragment)
        data['gates'].reverse()  # type: ignore[union-attr]
        _write_yaml(fragment, data)

    assert tuple(gate.name for gate in _load_catalog(catalog_tree).gates) == GATE_NAMES


def test_loader_rejects_missing_directory_and_symlink_escape(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[-1]
    fragment.unlink()
    with pytest.raises(ValueError, match='cannot load gate fragment'):
        _load_catalog(catalog_tree)

    outside = catalog_tree.parent / 'outside.yaml'
    outside.write_text('gates: []\n', encoding='utf-8')
    fragment.symlink_to(outside)
    with pytest.raises(ValueError, match='escapes gates directory'):
        _load_catalog(catalog_tree)


def test_loader_rejects_fragment_directory(catalog_tree: Path) -> None:
    fragment = catalog_tree.parent / GATE_FILES[-1]
    fragment.unlink()
    fragment.mkdir()

    with pytest.raises(ValueError, match='not a file'):
        _load_catalog(catalog_tree)


def test_loader_rejects_gate_directory_symlink_escape(catalog_tree: Path) -> None:
    gate_directory = catalog_tree.parent / 'gates'
    shutil.rmtree(gate_directory)
    gate_directory.symlink_to(catalog_tree.parent.parent, target_is_directory=True)

    with pytest.raises(ValueError, match='directory escapes catalog directory'):
        _load_catalog(catalog_tree)


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
        'cssOwnership': ('css-ownership',),
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


def test_css_ownership_has_one_java_owner_and_complete_inputs() -> None:
    gate = gate_by_name('cssOwnership')
    target_rules = {rule.target: rule for rule in gate.target_rules}

    assert gate.command is None
    assert gate.gradle_tasks == (':java:tests:quality-gates:runJavaQualityGates',)
    assert gate.java_rules == ('css-ownership',)
    assert target_rules['session-detail'].patterns == (
        'java/web/src/main/resources/static/css/**/*.css',
    )
    assert target_rules['python-standard'].patterns == ('scripts/gates/executor.py',)
    assert target_rules['acceptance-contracts'].patterns == ('tests/gates/test_executor.py',)
    assert target_rules['java-src'].patterns == (
        'java/tests/quality-gates/build.gradle.kts',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/AdvisoryQualityRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualityAdvisory.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualityContext.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualityRule.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualitySummary.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/QualityViolation.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/core/RepositorySourceSet.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/core/RepositorySourceSetTest.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/cli/QualityGateCli.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/PythonTextSemantics.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/ArtifactPairPublisher.java',
        'java/tests/quality-gates/src/main/java/com/feipi/session/browser/quality/gates/rules/web/CssOwnershipRule.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/cli/QualityGateCliTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/core/QualityViolationTest.java',
        'java/tests/quality-gates/src/test/java/com/feipi/session/browser/quality/gates/rules/web/CssOwnershipRuleTest.java',
    )


def test_executor_change_runs_tests_gates_through_python_coverage() -> None:
    gate = gate_by_name('pythonCoverage')
    target_rules = {rule.target: rule for rule in gate.target_rules}

    assert 'scripts/gates/executor.py' in target_rules['python-standard'].patterns
    assert target_rules['acceptance-contracts'].patterns == ('tests/gates/test_executor.py',)
    assert 'tests/gates' in gate.command.argv


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
