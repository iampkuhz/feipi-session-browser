"""验证 Python 安全检查保持锁文件、网络失败与高危源码语义。"""

from __future__ import annotations

import subprocess

from scripts.checks.repository import check_python_security as security


def _completed(
    returncode: int = 0, stdout: str = '', stderr: str = ''
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_security_check_runs_export_audit_and_bandit_in_order(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], str | None]] = []
    results = iter((_completed(stdout='locked requirements'), _completed(), _completed()))

    monkeypatch.setattr(security.shutil, 'which', lambda name: f'/tool/{name}')

    def fake_run(command, *, root, input_text=None):
        assert root == tmp_path
        calls.append((command, input_text))
        return next(results)

    monkeypatch.setattr(security, '_run', fake_run)

    assert security.check(['--root', str(tmp_path)]).passed
    assert calls[0][0][:3] == ['/tool/uv', 'export', '--frozen']
    assert calls[1][0][1:3] == ['-m', 'pip_audit']
    assert calls[1][1] == 'locked requirements'
    assert calls[2][0][1:3] == ['-m', 'bandit']


def test_security_check_preserves_network_error_for_gate_blocked_mapping(
    monkeypatch, tmp_path
) -> None:
    calls = 0

    monkeypatch.setattr(security.shutil, 'which', lambda _name: '/tool/uv')

    def fake_run(command, *, root, input_text=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _completed(stdout='locked requirements')
        return _completed(1, stderr='requests.exceptions.SSLError: certificate failed')

    monkeypatch.setattr(security, '_run', fake_run)

    result = security.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'requests.exceptions.SSLError' in result.diagnostics[0].message
    assert calls == 2


def test_security_check_fails_closed_when_uv_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(security.shutil, 'which', lambda _name: None)

    result = security.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'command not found' in result.diagnostics[0].message


def test_security_environment_drops_proxy_unless_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.invalid')
    monkeypatch.delenv('SESSION_BROWSER_AUDIT_USE_PROXY', raising=False)
    assert 'HTTPS_PROXY' not in security._environment()

    monkeypatch.setenv('SESSION_BROWSER_AUDIT_USE_PROXY', '1')
    assert security._environment()['HTTPS_PROXY'] == 'http://proxy.invalid'


def test_failure_diagnostic_is_bounded_redacted_and_keeps_network_marker() -> None:
    noisy_lines = [f'line-{index} token=private-{index}' for index in range(100)]
    noisy_lines.insert(50, 'requests.exceptions.ProxyError: proxy unavailable')
    process = _completed(1, stderr='\n'.join(noisy_lines))

    result = security._failure('pip-audit', process)
    message = result.diagnostics[0].message

    assert len(message) <= security._MAX_DIAGNOSTIC_CHARS + 64
    assert '[diagnostic truncated]' in message
    assert 'private-' not in message
    assert 'token=<redacted>' in message
    assert 'requests.exceptions.ProxyError' in message
