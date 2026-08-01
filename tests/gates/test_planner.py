"""changed-files 分类、tier 过滤与 Phase 1 golden plan contract。"""

import json
from pathlib import Path

from scripts.gates.catalog import GATES, TARGETS
from scripts.gates.planner import plan, required_gates_for_target

GOLDEN = Path(__file__).with_name('fixtures') / 'planner_golden.json'


def test_phase1_target_gate_baseline_is_exact() -> None:
    baseline = json.loads(GOLDEN.read_text(encoding='utf-8'))
    tiers = {gate.name: gate.tiers for gate in GATES}
    actual = {
        target.name: [
            name for name in required_gates_for_target(target.name) if 'required' in tiers[name]
        ]
        for target in TARGETS
    }
    assert actual == baseline['qualityTargets']
    assert len({name for names in actual.values() for name in names}) == baseline['uniqueGateCount']


def test_phase1_changed_files_plans_are_exact() -> None:
    baseline = json.loads(GOLDEN.read_text(encoding='utf-8'))
    for name, expected in baseline['scenarios'].items():
        changed_files = (
            ['scripts/checks/source/check_code_comment_language.py']
            if name == 'python-policy'
            else expected['changedFiles']
        )
        actual = plan(changed_files)
        assert list(actual.raw_targets) == expected['rawTargets'], name
        assert list(actual.effective_targets) == expected['effectiveTargets'], name
        assert {
            target.target: [gate.name for gate in target.gates] for target in actual.targets
        } == expected['gatesByTarget'], name
        assert sum(len(target.gates) for target in actual.targets) == expected['gateCount'], name


def test_required_plan_filters_full_only_gate() -> None:
    required = plan(['build.gradle.kts'], tier='required')
    full = plan(
        [],
        list(required.raw_targets or ('java-src',)),
        tier='full',
        incremental=False,
    )
    assert 'javaApiSnapshot' not in {gate.name for gate in required.logical_gates}
    assert 'javaApiSnapshot' in {gate.name for gate in full.logical_gates}


def test_declarative_catalog_change_triggers_gate_service_contracts() -> None:
    gate_plan = plan(['config/gates.yaml'])

    assert gate_plan.raw_targets == ('python-standard',)
    names = {gate.name for gate in gate_plan.logical_gates}
    assert {'ignoredTrackedFiles', 'misplacedGeneratedPaths', 'repoStructure'} <= names


def test_technical_terms_policy_triggers_both_language_owners() -> None:
    gate_plan = plan(['config/technical-terms.json'])

    assert gate_plan.raw_targets == ('java-build',)
    assert gate_plan.effective_targets == ('java-build',)
    names = [gate.name for gate in gate_plan.logical_gates]
    assert {'javaChineseComments', 'scriptCommentLanguage'} <= set(names)
    assert names.count('javaChineseComments') == 1
    assert names.count('scriptCommentLanguage') == 1


def test_script_change_triggers_script_comment_owner() -> None:
    gate_plan = plan(['scripts/checks/source/check_code_comment_language.py'])

    names = [gate.name for gate in gate_plan.logical_gates]
    assert gate_plan.raw_targets[:1] == ('python-standard',)
    assert names.count('scriptCommentLanguage') == 1


def test_web_change_does_not_trigger_script_comment_owner() -> None:
    gate_plan = plan(['java/web/src/main/resources/static/css/session-detail.css'])

    assert 'scriptCommentLanguage' not in {gate.name for gate in gate_plan.logical_gates}


def test_kotlin_source_selects_only_compatible_java_comment_rule() -> None:
    gate_plan = plan(['java/sample/src/main/kotlin/example/Foo.kt'])

    assert gate_plan.raw_targets == ('java-src',)
    assert gate_plan.effective_targets == ('java-src',)
    names = [gate.name for gate in gate_plan.logical_gates]
    assert names.count('javaChineseComments') == 1
    assert 'javaCheck' not in names
    assert 'javaRecordComponentJavadocs' not in names
    assert 'noJavaSuppressWarnings' not in names


def test_java_source_dominates_build_without_duplicate_logical_gates() -> None:
    gate_plan = plan(
        [
            'java/app-cli/src/main/java/com/feipi/session/browser/cli/App.java',
            'build.gradle.kts',
        ]
    )

    assert gate_plan.raw_targets[:2] == ('java-src', 'java-build')
    assert 'java-build' not in gate_plan.effective_targets
    names = [gate.name for gate in gate_plan.logical_gates]
    assert len(names) == len(set(names))
    assert names.count('javaCheck') == 1
    assert names.count('reuseStandardCpd') == 1
    assert names.count('reuseAnalyzeIncremental') == 1
