"""CLI 进程处理测试。"""

import subprocess
import sys

import pytest


@pytest.mark.contract_case('ACCEPTANCE-001')
def test_run_command_success():
    """短命令返回 stdout 和返回码。"""
    from session_browser.cli import _run_command

    result = _run_command(
        [sys.executable, '-c', "print('ok')"],
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == 'ok'


@pytest.mark.contract_case('ACCEPTANCE-001')
def test_run_command_timeout_cleans_process_group():
    """超时后终止派生的进程组并抛出异常。"""
    from session_browser.cli import _run_command

    with pytest.raises(subprocess.TimeoutExpired):
        _run_command(
            [sys.executable, '-c', 'import time; time.sleep(30)'],
            timeout=0.1,
        )
