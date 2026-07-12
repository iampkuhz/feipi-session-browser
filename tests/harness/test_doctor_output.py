"""Contract tests for concise harness doctor output."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


def _doctor_fixture(tmp_path: Path, *, include_agents: bool = True) -> tuple[Path, Path]:
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
    (root / 'openspec' / 'changes').mkdir(parents=True, exist_ok=True)

    fake_python = root / 'fake-python'
    fake_python.write_text(
        '#!/usr/bin/env bash\n'
        'if [[ "$*" == *"python_env.py resolve"* ]]; then\n'
        '  printf "%s\\n" "$0"\n'
        'else\n'
        '  echo "Total: 0"\n'
        'fi\n',
        encoding='utf-8',
    )
    fake_python.chmod(0o755)
    venv_python = root / '.venv' / 'bin' / 'python'
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(fake_python)
    return doctor, fake_python


def _run_doctor(doctor: Path, python: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['SESSION_BROWSER_PYTHON'] = str(python)
    return subprocess.run(
        ['bash', str(doctor), *args],
        cwd=doctor.parents[2],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


@pytest.mark.contract_case('HOOK-HARNESS-009')
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
