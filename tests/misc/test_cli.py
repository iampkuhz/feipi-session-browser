"""Tests for CLI process handling."""

import subprocess
import sys

import pytest


def test_run_command_success():
    """Short commands return stdout and return code."""
    from session_browser.cli import _run_command

    result = _run_command(
        [sys.executable, "-c", "print('ok')"],
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"


def test_run_command_timeout_cleans_process_group():
    """Timeouts are surfaced after terminating the spawned process group."""
    from session_browser.cli import _run_command

    with pytest.raises(subprocess.TimeoutExpired):
        _run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.1,
        )
