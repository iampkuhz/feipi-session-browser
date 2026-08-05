"""验证 Gradle-owned incremental PMD CPD Gate 的双模式契约。"""

from pathlib import Path

from scripts.gates.catalog import gate_by_name
from scripts.gates.model import RunKind

REPO_ROOT = Path(__file__).resolve().parents[2]


def _root_build_text() -> str:
    return (REPO_ROOT / 'build.gradle.kts').read_text(encoding='utf-8')


def test_catalog_registers_only_the_gradle_owner() -> None:
    gate = gate_by_name('reuseStandardCpd')

    assert gate.run.kind is RunKind.GRADLE_TASK
    assert gate.run.incremental.tasks == ('reuseStandardCpd',)
    assert gate.run.full.tasks == ('reuseStandardCpd',)


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
