"""Contract tests for concise harness doctor output."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def _doctor_fixture(
    tmp_path: Path,
    *,
    include_agents: bool = True,
    include_changes: bool = True,
) -> tuple[Path, Path]:
    """Create the smallest filesystem accepted by the doctor shell contract."""
    root = tmp_path / 'repo'
    script_dir = root / 'scripts' / 'harness'
    script_dir.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / 'scripts' / 'harness' / 'doctor.sh'
    doctor = script_dir / 'doctor.sh'
    shutil.copy2(source, doctor)

    doctor_source = source.read_text(encoding='utf-8')
    files = re.findall(r'^check_file ([^\s#]+)', doctor_source, flags=re.MULTILINE)
    directories = re.findall(r'^check_dir ([^\s#]+)', doctor_source, flags=re.MULTILINE)
    if not include_agents:
        files.remove('AGENTS.md')
    for relative in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}\n' if relative.endswith('.json') else '\n', encoding='utf-8')
    for relative in directories:
        (root / relative).mkdir(parents=True, exist_ok=True)
    if include_changes:
        (root / 'openspec' / 'changes').mkdir(parents=True, exist_ok=True)

    fake_python = root / 'fake-python'
    fake_python.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "${DOCTOR_CALL_LOG:?}"\n'
        'if [[ "$*" == *"python_env.py resolve"* ]]; then\n'
        '  printf "%s\\n" "$0"\n'
        'else\n'
        '  echo "Total: 0"\n'
        'fi\n',
        encoding='utf-8',
    )
    fake_python.chmod(0o755)
    venv_python = root / '.local' / 'python' / 'venv' / 'bin' / 'python'
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(fake_python)
    fake_uv = root / 'uv'
    fake_uv.write_text('#!/usr/bin/env bash\nexit 0\n', encoding='utf-8')
    fake_uv.chmod(0o755)
    return doctor, fake_python


def _run_doctor(doctor: Path, python: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['SESSION_BROWSER_PYTHON'] = str(python)
    env['DOCTOR_CALL_LOG'] = str(doctor.parents[2] / '.doctor-call-log')
    env['PATH'] = f'{doctor.parents[2]}:{env.get("PATH", "")}'
    return subprocess.run(
        ['bash', str(doctor), *args],
        cwd=doctor.parents[2],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    """Return repository contents, excluding the test-only invocation log."""
    snapshot: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if relative == '.doctor-call-log':
            continue
        if path.is_symlink():
            snapshot[relative] = ('symlink', os.readlink(path))
        elif path.is_dir():
            snapshot[relative] = ('dir', '')
        else:
            snapshot[relative] = ('file', path.read_bytes())
    return snapshot


@pytest.mark.contract_case('HOOK-HARNESS-009', 'HOOK-HARNESS-014')
def test_doctor_success_is_one_line_by_default(tmp_path: Path):
    doctor, python = _doctor_fixture(tmp_path)

    proc = _run_doctor(doctor, python)

    assert proc.returncode == 0, proc.stdout
    assert proc.stdout.strip().count('\n') == 0
    assert proc.stdout.startswith('DOCTOR_RESULT status=PASS')


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_doctor_verbose_keeps_pass_details(tmp_path: Path):
    doctor, python = _doctor_fixture(tmp_path)

    proc = _run_doctor(doctor, python, '--verbose')

    assert proc.returncode == 0, proc.stdout
    assert '[PASS] file exists: AGENTS.md' in proc.stdout
    assert 'DOCTOR_RESULT status=PASS' in proc.stdout


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_doctor_failure_names_the_failed_check(tmp_path: Path):
    doctor, python = _doctor_fixture(tmp_path, include_agents=False)

    proc = _run_doctor(doctor, python)

    assert proc.returncode == 1
    assert '[FAIL] missing file: AGENTS.md' in proc.stdout
    assert 'DOCTOR_RESULT status=FAIL' in proc.stdout


@pytest.mark.contract_case('HOOK-HARNESS-009', 'HOOK-HARNESS-014')
def test_doctor_is_read_only_and_does_not_run_quality_gates(tmp_path: Path):
    doctor, python = _doctor_fixture(tmp_path)
    root = doctor.parents[2]
    before = _tree_snapshot(root)

    proc = _run_doctor(doctor, python)

    assert proc.returncode == 0, proc.stdout
    assert _tree_snapshot(root) == before
    calls = (root / '.doctor-call-log').read_text(encoding='utf-8')
    assert '-m scripts.checks' not in calls
    assert 'scripts/gates/cli.py' not in calls
    assert 'scripts.gates.cli' not in calls
    assert 'compileall' not in calls


@pytest.mark.contract_case('HOOK-HARNESS-009', 'HOOK-HARNESS-014')
def test_doctor_does_not_create_missing_openspec_changes(tmp_path: Path):
    doctor, python = _doctor_fixture(tmp_path, include_changes=False)
    changes = doctor.parents[2] / 'openspec' / 'changes'

    proc = _run_doctor(doctor, python)

    assert proc.returncode == 0, proc.stdout
    assert not changes.exists()
    assert '[WARN] openspec/changes/ 不存在' in proc.stdout
    assert 'DOCTOR_RESULT status=PASS' in proc.stdout
