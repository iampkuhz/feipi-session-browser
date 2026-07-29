"""Gradle-owned incremental PMD CPD quality gate contracts."""

from pathlib import Path

from scripts.gates.catalog import gate_by_name

REPO_ROOT = Path(__file__).resolve().parents[2]


def _root_build_text() -> str:
    return (REPO_ROOT / 'build.gradle.kts').read_text(encoding='utf-8')


def test_catalog_registers_only_the_gradle_owner() -> None:
    gate = gate_by_name('reuseStandardCpd')

    assert gate.command is None
    assert gate.gradle_tasks == ('reuseStandardCpd',)
    assert gate.changed_files_input.value == 'environment'


def test_gradle_owner_uses_changed_files_json_and_incremental_default() -> None:
    text = _root_build_text()

    assert 'providers.environmentVariable("QUALITY_CHANGED_FILES")' in text
    assert (
        'if (qualityGateTier.equals("full", ignoreCase = true)) "full" else "incremental"' in text
    )
    assert '"QUALITY_CHANGED_FILES must be valid JSON."' in text
    assert '"QUALITY_CHANGED_FILES must contain only string paths."' in text


def test_gradle_owner_keeps_exact_file_list_and_never_directory_scan() -> None:
    text = _root_build_text()
    start = text.index('fun reuseCpdArgs(')
    end = text.index('fun writeReuseCpdSummary(', start)
    function_text = text[start:end]

    assert 'add("--file-list")' in function_text
    assert 'add("--dir")' not in function_text


def test_gradle_owner_reports_generic_blocking_task_marker() -> None:
    text = _root_build_text()

    assert '"GATE_TASK_RESULT task=${task.path} status=BLOCKED reason=${exc.reasonCode}"' in text
    assert '"policy-changed"' in text
    assert '"invalid-changed-files-json"' in text
