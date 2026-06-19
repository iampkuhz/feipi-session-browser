"""Regression tests for warning-as-error pytest entrypoint behavior."""
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


def test_session_browser_test_fails_on_pytest_warning(tmp_path):
    test_file = tmp_path / "test_warning_gate.py"
    test_file.write_text(
        "import warnings\n\n"
        "def test_warning_after_trigger():\n"
        "    warnings.warn('gate must reject this warning', UserWarning)\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["./scripts/session-browser.sh", "test", str(test_file)],
        cwd=repo_root,
        env={**os.environ, "SESSION_BROWSER_PYTHON": sys.executable},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )

    assert proc.returncode != 0
    assert "UserWarning: gate must reject this warning" in proc.stdout
