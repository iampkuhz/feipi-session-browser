"""验证 javaDuplicationAudit single recipe 中的 incremental PMD CPD owner 契约。"""

from pathlib import Path

from scripts.gates.catalog import RecipeStepKind, gate_by_name

REPO_ROOT = Path(__file__).resolve().parents[2]


def _root_build_text() -> str:
    return (REPO_ROOT / 'build.gradle.kts').read_text(encoding='utf-8')


def test_catalog_registers_cpd_in_java_reuse_policy_recipe() -> None:
    gate = gate_by_name('javaDuplicationAudit')

    assert tuple((step.name, step.kind, step.tasks) for step in gate.recipe.steps) == (
        ('reuseStandardCpd', RecipeStepKind.GRADLE_TASK, ('reuseStandardCpd',)),
    )


def test_root_check_owns_pmd_zero_skip_and_the_java_rule_registry() -> None:
    root_text = _root_build_text()
    quality_build_text = (REPO_ROOT / 'java/tests/quality-gates/build.gradle.kts').read_text(
        encoding='utf-8'
    )

    assert 'dependsOn(leafSubprojects.map { "${it.path}:check" })' in root_text
    assert 'dependsOn(verifyNoSkippedJavaTests)' in root_text
    assert 'dependsOn(":java:tests:quality-gates:runJavaQualityGates")' in root_text
    assert (
        '.orElse("java-comment-language,record-component-javadocs,no-pmd-suppressions")'
        in quality_build_text
    )
    assert 'reuseAnalyzeIncremental' not in root_text
    assert 'incremental-result.json' not in root_text
    assert '"delegatedTo": "pmdMain"' not in root_text


def test_gradle_owner_uses_changed_files_json_and_incremental_default() -> None:
    text = _root_build_text()

    assert 'providers.environmentVariable("QUALITY_CHANGED_FILES")' in text
    assert 'providers.environmentVariable("QUALITY_EXECUTION_MODE")' in text
    assert 'explicitMode ?: qualityExecutionMode ?: "incremental"' in text
    assert 'QUALITY_GATE_' + 'TIER' not in text
    assert '"QUALITY_CHANGED_FILES must be valid JSON."' in text
    assert '"QUALITY_CHANGED_FILES must contain only string paths."' in text


def test_incremental_owner_expands_unsafe_configuration_changes_internally() -> None:
    """配置改动由 Gate 自己扩大输入，不要求外部把 incremental 偷换成 full。"""
    text = _root_build_text()

    assert 'requiresCompleteCpdInput' in text
    assert 'QUALITY_CHANGED_FILES(expanded-to-all-sources)' in text
    assert 'explicit full mode is required' not in text


def test_gradle_owner_keeps_exact_file_list_and_never_directory_scan() -> None:
    text = _root_build_text()
    start = text.index('fun reuseCpdArgs(')
    end = text.index('fun writeReuseCpdSummary(', start)
    function_text = text[start:end]

    assert 'add("--file-list")' in function_text
    assert 'add("--dir")' not in function_text


def test_gradle_owner_reports_structured_blocked_and_fail_task_markers() -> None:
    text = _root_build_text()

    assert '"GATE_TASK_RESULT task=${task.path} status=BLOCKED"' in text
    assert '"GATE_TASK_RESULT task=${task.path} status=FAIL reason=${exc.reasonCode}"' in text
    assert '"input-unavailable"' in text


def test_cpd_runtime_is_local_to_execution_and_keeps_same_file_analysis() -> None:
    text = _root_build_text()
    action = text.split('private class ReuseStandardCpdAction(', 1)[1].split(
        '\ngradle.projectsEvaluated {', 1
    )[0]
    fields = action.split('override fun execute(task: Task)', 1)[0]

    assert 'URLClassLoader' not in fields
    assert 'java.lang.reflect.Method' not in fields
    assert 'ProcessBuilder' not in action
    assert 'getDeclaredMethod("mainWithoutExit", Array<String>::class.java)' in action
    assert 'cpdInputFiles.forEach { sourceFile ->' in action
    assert 'listOf(sourceFile)' in action
    assert '"tool-execution-error"' in action
