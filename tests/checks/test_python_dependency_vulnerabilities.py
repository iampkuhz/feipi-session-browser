"""验证 Python 锁定依赖漏洞检查的串行、失败和诊断语义。"""

from __future__ import annotations

import subprocess

from scripts.checks.repository import check_python_dependency_vulnerabilities as audit


def _completed(
    returncode: int = 0, stdout: str = '', stderr: str = ''
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_dependency_vulnerability_check_exports_then_audits(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], str | None]] = []
    results = iter((_completed(stdout='locked requirements'), _completed()))
    monkeypatch.setattr(audit.shutil, 'which', lambda name: f'/tool/{name}')

    def fake_run(command, *, root, input_text=None):
        assert root == tmp_path
        calls.append((command, input_text))
        return next(results)

    monkeypatch.setattr(audit, '_run', fake_run)

    assert audit.check(['--root', str(tmp_path)]).passed
    assert calls[0][0][:3] == ['/tool/uv', 'export', '--frozen']
    assert '--extra' in calls[0][0]
    assert calls[1][0][1:3] == ['-m', 'pip_audit']
    assert calls[1][1] == 'locked requirements'
    assert len(calls) == 2


def test_dependency_vulnerability_check_fails_closed_when_uv_is_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(audit.shutil, 'which', lambda _name: None)

    result = audit.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'command not found' in result.diagnostics[0].message


def test_dependency_vulnerability_check_stops_when_export_fails(monkeypatch, tmp_path) -> None:
    calls = 0
    monkeypatch.setattr(audit.shutil, 'which', lambda _name: '/tool/uv')

    def fake_run(command, *, root, input_text=None):
        nonlocal calls
        calls += 1
        return _completed(2, stderr='lock export failed')

    monkeypatch.setattr(audit, '_run', fake_run)

    result = audit.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'uv export FAIL' in result.diagnostics[0].message
    assert 'lock export failed' in result.diagnostics[0].message
    assert calls == 1


def test_dependency_vulnerability_check_reports_audit_vulnerability(monkeypatch, tmp_path) -> None:
    results = iter(
        (
            _completed(stdout='locked requirements'),
            _completed(1, stdout='package 1.0 GHSA-example'),
        )
    )
    monkeypatch.setattr(audit.shutil, 'which', lambda _name: '/tool/uv')
    monkeypatch.setattr(audit, '_run', lambda *args, **kwargs: next(results))

    result = audit.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'pip-audit FAIL' in result.diagnostics[0].message
    assert 'GHSA-example' in result.diagnostics[0].message


def test_dependency_vulnerability_check_preserves_network_error(monkeypatch, tmp_path) -> None:
    results = iter(
        (
            _completed(stdout='locked requirements'),
            _completed(1, stderr='requests.exceptions.SSLError: certificate failed'),
        )
    )
    monkeypatch.setattr(audit.shutil, 'which', lambda _name: '/tool/uv')
    monkeypatch.setattr(audit, '_run', lambda *args, **kwargs: next(results))

    result = audit.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'requests.exceptions.SSLError' in result.diagnostics[0].message


def test_dependency_vulnerability_environment_drops_proxy_unless_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.invalid')
    monkeypatch.delenv('SESSION_BROWSER_AUDIT_USE_PROXY', raising=False)
    assert 'HTTPS_PROXY' not in audit._environment()

    monkeypatch.setenv('SESSION_BROWSER_AUDIT_USE_PROXY', '1')
    assert audit._environment()['HTTPS_PROXY'] == 'http://proxy.invalid'


def test_failure_diagnostic_is_bounded_redacted_and_keeps_network_marker() -> None:
    noisy_lines = [f'line-{index} token=private-{index}' for index in range(100)]
    noisy_lines.insert(50, 'requests.exceptions.ProxyError: proxy unavailable')
    process = _completed(1, stderr='\n'.join(noisy_lines))

    result = audit._failure('pip-audit', process)
    message = result.diagnostics[0].message

    assert len(message) <= audit._MAX_DIAGNOSTIC_CHARS + 96
    assert '[diagnostic truncated]' in message
    assert 'private-' not in message
    assert 'token=<redacted>' in message
    assert 'requests.exceptions.ProxyError' in message
