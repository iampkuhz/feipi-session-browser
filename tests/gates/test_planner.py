"""有序 multi-target classification 与 tier/planner contract。"""

import pytest
from scripts.gates.planner import (
    applicable_gates_for_target,
    classify_path,
    effective_targets,
    plan,
    required_gates_for_target,
    required_quality_targets,
)


@pytest.mark.parametrize(
    ('path', 'targets'),
    [
        ('tests/gates/test_catalog.py', ('acceptance-contracts', 'python-standard')),
        (
            'tests/ui/test_web_static_contract.py',
            ('session-detail', 'acceptance-contracts', 'python-standard'),
        ),
        ('tests/playwright/specs/detail.spec.ts', ('acceptance-contracts',)),
        (
            'scripts/checks/web/check_session_detail_static.py',
            ('session-detail', 'python-standard'),
        ),
        (
            'scripts/checks/web/check_js_action_handlers.py',
            ('session-detail', 'python-standard'),
        ),
        ('scripts/harness/python_env.py', ('harness', 'python-standard')),
        ('scripts/openspec/validate_layout.py', ('harness', 'python-standard')),
        ('README.md', ()),
    ],
)
def test_path_classification_returns_ordered_targets(path: str, targets: tuple[str, ...]) -> None:
    classification = classify_path(path)
    assert classification.targets == targets
    assert classification.requires_quality_gate is bool(targets)


def test_targets_are_stably_deduplicated_across_paths_and_scan_trigger_is_appended() -> None:
    assert required_quality_targets(
        [
            'tests/gates/test_catalog.py',
            'scripts/checks/web/check_session_detail_static.py',
        ]
    ) == ['acceptance-contracts', 'python-standard', 'session-detail', 'scan-script-smoke']
    assert required_quality_targets(
        [
            'scripts/checks/web/check_session_detail_static.py',
            'tests/gates/test_catalog.py',
        ]
    ) == ['session-detail', 'python-standard', 'acceptance-contracts', 'scan-script-smoke']


def test_only_explicit_target_dominance_is_applied() -> None:
    assert effective_targets(['java-src', 'java-build', 'python-standard']) == [
        'java-src',
        'python-standard',
    ]
    assert effective_targets(['acceptance-contracts', 'session-detail', 'python-standard']) == [
        'acceptance-contracts',
        'session-detail',
        'python-standard',
    ]
    with pytest.raises(ValueError, match='Unknown quality target'):
        effective_targets(['missing'])


def test_multi_target_plan_has_one_stable_responsibility_per_business_gate() -> None:
    result = plan(
        [
            'docs/acceptance-contracts/features/COMMON.md',
            'java/web/src/main/resources/static/css/main.css',
        ],
        incremental=False,
    )
    names = [gate.name for gate in result.logical_gates]
    assert names.count('acceptanceContracts') == 1
    assert names.count('sessionDetailStaticTests') == 1
    assert 'pytest' not in names


def test_python_test_selects_acceptance_harness_and_python_standard_without_duplicate_business_gate() -> (
    None
):
    result = plan(['tests/gates/test_executor.py'])
    assert result.raw_targets == ('acceptance-contracts', 'python-standard')
    names = [gate.name for gate in result.logical_gates]
    assert names.count('acceptanceContracts') == 1
    assert names.count('pythonHarnessTests') == 1
    assert 'sessionDetailStaticTests' not in names


def test_full_only_dependency_vulnerability_gate_is_not_in_required() -> None:
    required = plan(['uv.lock'], tier='required')
    full = plan(['uv.lock'], tier='full')
    assert 'pythonDependencyVulnerabilities' not in [g.name for g in required.logical_gates]
    assert 'pythonDependencyVulnerabilities' in [g.name for g in full.logical_gates]


@pytest.mark.contract_case('J1-040-001')
@pytest.mark.parametrize(
    ('path', 'category', 'target'),
    [
        ('java/core-domain/src/main/java/com/feipi/Foo.java', 'java-src', 'java-src'),
        ('java/tests/architecture/src/test/java/com/feipi/BarTest.java', 'java-src', 'java-src'),
        (
            'gradle/build-logic/src/main/kotlin/feipi.java-base.gradle.kts',
            'java-build',
            'java-build',
        ),
        ('gradle/libs.versions.toml', 'java-build', 'java-build'),
        ('settings.gradle.kts', 'java-build', 'java-build'),
        ('build.gradle.kts', 'java-root-dsl', 'java-build'),
        ('gradle.properties', 'java-root-dsl', 'java-build'),
    ],
)
def test_java_paths_keep_their_owned_classification(path: str, category: str, target: str) -> None:
    classification = classify_path(path)
    assert classification.category == category
    assert classification.targets == (target,)
    assert classification.allowed is True


@pytest.mark.contract_case('JR-020-001')
def test_kotlin_source_uses_the_java_source_target() -> None:
    classification = classify_path('java/sample/src/main/kotlin/example/Foo.kt')
    assert classification.category == 'java-src'
    assert classification.targets == ('java-src',)
    assert classification.allowed is True


@pytest.mark.contract_case('J1-040-002')
@pytest.mark.parametrize(
    'path',
    [
        'gradlew',
        'gradlew.bat',
        'settings-gradle.lockfile',
        'gradle/wrapper/gradle-wrapper.jar',
        'gradle/verification-metadata.xml',
    ],
)
def test_extended_gradle_paths_are_java_build_inputs(path: str) -> None:
    classification = classify_path(path)
    assert classification.targets == ('java-build',)
    assert classification.requires_quality_gate
    assert classification.allowed is True


@pytest.mark.contract_case('J1-040-003')
@pytest.mark.parametrize(
    ('path', 'category', 'allowed'),
    [
        ('some/random/file.java', 'java-src-unknown', False),
        ('random.gradle.kts', 'java-build-unknown', False),
        ('java/core-domain/src/main/java/com/feipi/Foo.java', 'java-src', True),
        ('build.gradle.kts', 'java-root-dsl', True),
    ],
)
def test_java_classification_is_first_match_and_fails_closed(
    path: str, category: str, allowed: bool
) -> None:
    classification = classify_path(path)
    assert classification.category == category
    assert classification.targets in {('java-src',), ('java-build',)}
    assert classification.requires_quality_gate
    assert classification.allowed is allowed


@pytest.mark.contract_case('J1-040-004')
@pytest.mark.parametrize(
    ('path', 'normalized', 'target'),
    [
        (
            r'java\core-domain\src\main\java\com\feipi\Foo.java',
            'java/core-domain/src/main/java/com/feipi/Foo.java',
            'java-src',
        ),
        (r'.\gradlew', 'gradlew', 'java-build'),
    ],
)
def test_windows_java_paths_are_normalized(path: str, normalized: str, target: str) -> None:
    classification = classify_path(path)
    assert classification.file == normalized
    assert classification.targets == (target,)


@pytest.mark.contract_case('J1-040-005')
def test_java_multi_file_targets_are_stably_deduplicated() -> None:
    targets = required_quality_targets(
        [
            'java/core-domain/src/main/java/com/feipi/A.java',
            'java/app-cli/src/main/java/com/feipi/B.java',
            'build.gradle.kts',
        ]
    )
    assert targets == ['java-src', 'java-build', 'scan-script-smoke']
    assert required_quality_targets(
        [
            'java/a/src/main/java/A.java',
            'java/b/src/main/java/B.java',
        ]
    ) == ['java-src']


@pytest.mark.contract_case('J1-040-006')
def test_java_target_dominance_is_explicit_and_order_preserving() -> None:
    from scripts.gates.catalog import target_by_name

    assert target_by_name('java-src').includes == ('java-build',)
    assert effective_targets(['java-src', 'java-build']) == ['java-src']
    assert effective_targets(['java-build']) == ['java-build']
    assert effective_targets(['java-src', 'harness']) == ['java-src', 'harness']


@pytest.mark.contract_case('J1-040-010')
@pytest.mark.parametrize(
    ('target', 'path'),
    [
        ('java-build', 'gradlew'),
        ('java-build', 'settings-gradle.lockfile'),
        ('java-src', 'some/random/File.java'),
    ],
)
def test_java_gate_inventory_applies_to_supported_and_fail_closed_paths(
    target: str, path: str
) -> None:
    gates = applicable_gates_for_target(target, [path])
    assert 'javaCheck' in gates
    if target == 'java-src':
        assert {'javaChineseComments', 'noJavaTestSkips'} <= set(required_gates_for_target(target))


@pytest.mark.contract_case('J1-040-011')
def test_java_target_planning_is_deterministic() -> None:
    assert effective_targets(['harness', 'java-src', 'java-build']) == ['harness', 'java-src']
    files = [
        'build.gradle.kts',
        'java/core-domain/src/main/java/com/feipi/Foo.java',
        '.claude/hooks/stop.sh',
    ]
    assert required_quality_targets(files) == required_quality_targets(files)


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('scripts/session-browser.sh', True),
        ('java/scan-engine/src/main/java/com/feipi/scan/FullScanEngine.java', True),
        ('java/sources/src/main/java/com/feipi/source/ClaudeSourceAdapter.java', True),
        ('java/index-sqlite/src/main/java/com/feipi/index/ConnectionFactory.java', True),
        ('java/app-cli/src/main/java/com/feipi/cli/ScanCommand.java', True),
        ('scripts/checks/gate_executor.py', True),
        ('java/web/src/main/resources/static/css/main.css', False),
    ],
)
def test_scan_smoke_trigger_preserves_historical_paths(path: str, expected: bool) -> None:
    assert ('scan-script-smoke' in required_quality_targets([path])) is expected


def test_java_policy_files_are_known_java_build_inputs() -> None:
    for path in (
        'config/architecture/java-modules.yaml',
        'config/reuse-policy/policy.json',
        'config/pmd/pmd.xml',
        'java/data/build.gradle.kts',
    ):
        classification = classify_path(path)
        assert classification.targets == ('java-build',)
        assert classification.allowed is True
