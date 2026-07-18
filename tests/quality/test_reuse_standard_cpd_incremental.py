"""Contract tests for incremental PMD CPD quality gate input."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.checks import run_reuse_standard_cpd as cpd


def _write(path: Path, text: str = 'class X {}\n') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def test_default_mode_is_incremental(monkeypatch) -> None:
    """Wrapper CLI defaults to incremental mode, not full mode."""
    monkeypatch.delenv('FEIPI_REUSE_CPD_MODE', raising=False)
    monkeypatch.delenv('QUALITY_REUSE_CPD_MODE', raising=False)

    args = cpd.build_parser().parse_args([])

    assert args.mode == 'incremental'


def test_incremental_file_list_contains_only_changed_java_file(tmp_path: Path) -> None:
    """同目录只改一个文件时，file-list 不得包含未修改 sibling。"""
    changed = _write(
        tmp_path / 'java/app/src/main/java/com/example/Changed.java',
        'class Changed {}\n',
    )
    unchanged = _write(
        tmp_path / 'java/app/src/main/java/com/example/Unchanged.java',
        'class Unchanged {}\n',
    )

    selected = cpd.select_incremental_java_files(
        tmp_path,
        ['java/app/src/main/java/com/example/Changed.java'],
    )
    file_list = cpd.write_cpd_file_list(
        tmp_path,
        selected,
        tmp_path / cpd.FILE_LIST_RELATIVE_PATH,
    )

    lines = file_list.read_text(encoding='utf-8').splitlines()
    assert lines == [changed.resolve().as_posix()]
    assert unchanged.resolve().as_posix() not in lines


def test_root_outputs_use_local_gradle_tree() -> None:
    """CPD wrapper writes only below the configured root Gradle output tree."""
    assert cpd.SUMMARY_RELATIVE_PATH == Path(
        '.local/gradle/root-build/reports/reuse-analysis/standard-cpd-summary.json'
    )
    assert cpd.FILE_LIST_RELATIVE_PATH == Path(
        '.local/gradle/root-build/tmp/reuse-standard-cpd/reuse-cpd-file-list.txt'
    )


def test_incremental_ignores_non_production_or_missing_files(tmp_path: Path) -> None:
    """CPD 增量输入只保留存在的 production Java 文件。"""
    prod = _write(tmp_path / 'java/core/src/main/java/com/example/Prod.java')
    _write(tmp_path / 'java/core/src/test/java/com/example/ProdTest.java')

    selected = cpd.select_incremental_java_files(
        tmp_path,
        [
            'java/core/src/main/java/com/example/Prod.java',
            'java/core/src/test/java/com/example/ProdTest.java',
            'java/core/src/main/java/com/example/Missing.java',
            'scripts/checks/gate_executor.py',
        ],
    )

    assert selected == ['java/core/src/main/java/com/example/Prod.java']
    assert (tmp_path / selected[0]).resolve() == prod.resolve()


def test_policy_change_blocks_in_default_incremental_mode(tmp_path: Path) -> None:
    """CPD policy change must not silently fall back to a full scan."""
    changed = json.dumps(['config/reuse-policy/policy.json'])

    rc = cpd.run_incremental(tmp_path, changed)

    assert rc == 2
    summary = json.loads((tmp_path / cpd.SUMMARY_RELATIVE_PATH).read_text(encoding='utf-8'))
    assert summary['status'] == 'BLOCKED'
    assert summary['mode'] == 'incremental'
    assert summary['fullScan'] is False
    assert summary['dirScanUsed'] is False
    assert summary['cpdInputCount'] == 0


def test_no_changed_java_is_noop_not_full_scan(tmp_path: Path, monkeypatch) -> None:
    """没有 changed production Java 时不调用 Gradle full CPD。"""

    def fail_run_gradle(command: list[str], repo_root: Path) -> int:
        raise AssertionError(
            f'Gradle should not run for no-op incremental CPD: {command} {repo_root}'
        )

    monkeypatch.setattr(cpd, 'run_gradle', fail_run_gradle)

    rc = cpd.run_incremental(tmp_path, json.dumps(['scripts/checks/gate_executor.py']))

    assert rc == 0
    summary = json.loads((tmp_path / cpd.SUMMARY_RELATIVE_PATH).read_text(encoding='utf-8'))
    assert summary['mode'] == 'incremental'
    assert summary['fullScan'] is False
    assert summary['dirScanUsed'] is False
    assert summary['cpdInputFiles'] == []


def test_incremental_gradle_command_uses_file_list_property(tmp_path: Path, monkeypatch) -> None:
    """Wrapper invokes Gradle incremental mode with an exact file-list property."""
    changed = _write(tmp_path / 'java/app/src/main/java/com/example/Changed.java')
    commands: list[list[str]] = []

    def capture_run_gradle(command: list[str], repo_root: Path) -> int:
        commands.append(command)
        assert repo_root == tmp_path
        return 0

    monkeypatch.setattr(cpd, 'run_gradle', capture_run_gradle)

    rc = cpd.run_incremental(
        tmp_path,
        json.dumps(['java/app/src/main/java/com/example/Changed.java']),
    )

    assert rc == 0
    assert commands, 'Gradle should run when there is a changed production Java file'
    command = commands[0]
    assert 'reuseStandardCpd' in command
    assert '-PfeipiReuseCpdMode=incremental' in command
    file_list_props = [part for part in command if part.startswith('-PfeipiReuseCpdFileList=')]
    assert len(file_list_props) == 1
    file_list = Path(file_list_props[0].split('=', 1)[1])
    assert file_list.read_text(encoding='utf-8').splitlines() == [changed.resolve().as_posix()]
    assert '--dir' not in command


def test_full_gradle_command_is_explicit() -> None:
    """Full CPD is available only as an explicit mode in the wrapper command."""
    command = cpd.build_gradle_command(Path('/repo'), 'full', None)

    assert command == [
        '/repo/gradlew',
        'reuseStandardCpd',
        '-PfeipiReuseCpdMode=full',
        '--console=plain',
    ]


def test_gradle_cpd_argument_builder_uses_file_list_not_dir() -> None:
    """Static contract: Gradle PMD CPD args use --file-list and do not use --dir."""
    build_file = Path(__file__).resolve().parents[2] / 'build.gradle.kts'
    text = build_file.read_text(encoding='utf-8')
    start = text.index('fun reuseCpdArgs(')
    end = text.index('fun writeReuseCpdSummary(', start)
    function_text = text[start:end]

    assert 'add("--file-list")' in function_text
    assert 'add("--dir")' not in function_text


def test_gradle_task_default_mode_is_incremental() -> None:
    """Gradle task must not default to full CPD when mode is omitted."""
    build_file = Path(__file__).resolve().parents[2] / 'build.gradle.kts'
    text = build_file.read_text(encoding='utf-8')

    assert '?: "incremental").lowercase()' in text
    assert '?: "full").lowercase()' not in text
