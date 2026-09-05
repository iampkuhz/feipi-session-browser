"""验证 Python 锁定依赖漏洞检查的串行、失败和诊断语义。"""

from __future__ import annotations

import os
import subprocess

import pytest
from scripts.gates.checks.repository import check_python_dependency_audit as audit


def _completed(
    returncode: int = 0, stdout: str = '', stderr: str = ''
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_python_dependency_audit_check_exports_then_audits(monkeypatch, tmp_path) -> None:
    calls: list[tuple[list[str], str | None]] = []
    results = iter((_completed(stdout='locked requirements'), _completed()))
    monkeypatch.setattr(audit.shutil, 'which', lambda name: f'/tool/{name}')

    def fake_run(command, *, root, input_text=None):
        assert root == tmp_path
        calls.append((command, input_text))
        return next(results)

    monkeypatch.setattr(audit, '_run', fake_run)

    assert audit.check(['--root', str(tmp_path)]).passed
    assert calls[0][0][:5] == [
        '/tool/uv',
        'export',
        '--project',
        str(tmp_path / 'scripts'),
        '--frozen',
    ]
    assert '--extra' in calls[0][0]
    assert calls[1][0][1:3] == ['-m', 'pip_audit']
    assert calls[1][1] == 'locked requirements'
    assert len(calls) == 2


def test_python_dependency_audit_check_fails_closed_when_uv_is_missing(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(audit.shutil, 'which', lambda _name: None)

    result = audit.check(['--root', str(tmp_path)])

    assert not result.passed
    assert result.status.value == 'FAIL'
    assert result.reason == 'runtime-missing'
    assert 'command not found' in result.diagnostics[0].message


def test_python_dependency_audit_check_stops_when_export_fails(monkeypatch, tmp_path) -> None:
    calls = 0
    monkeypatch.setattr(audit.shutil, 'which', lambda _name: '/tool/uv')

    def fake_run(command, *, root, input_text=None):
        nonlocal calls
        calls += 1
        return _completed(2, stderr='lock export failed')

    monkeypatch.setattr(audit, '_run', fake_run)

    result = audit.check(['--root', str(tmp_path)])

    assert not result.passed
    assert 'uv export' in result.diagnostics[0].message
    assert result.status.value == 'FAIL'
    assert result.reason == 'dependency-unavailable'
    assert 'lock export failed' in result.diagnostics[0].message
    assert calls == 1


def test_python_dependency_audit_check_reports_audit_vulnerability(monkeypatch, tmp_path) -> None:
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
    assert 'pip-audit' in result.diagnostics[0].message
    assert result.status.value == 'BLOCKED'
    assert 'GHSA-example' in result.diagnostics[0].message


def test_python_dependency_audit_check_preserves_network_error(monkeypatch, tmp_path) -> None:
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
    assert result.status.value == 'FAIL'
    assert result.reason == 'network-unavailable'
    assert 'requests.exceptions.SSLError' in result.diagnostics[0].message


@pytest.mark.parametrize(
    'name',
    (
        'HTTPS_PROXY',
        'HTTP_PROXY',
        'ALL_PROXY',
        'https_proxy',
        'http_proxy',
        'all_proxy',
        'NO_PROXY',
        'no_proxy',
        'REQUESTS_CA_BUNDLE',
        'SSL_CERT_FILE',
    ),
)
def test_python_dependency_audit_preserves_configured_transport(
    monkeypatch,
    tmp_path,
    name,
) -> None:
    value = (
        str(tmp_path / 'ca.pem') if name.endswith(('BUNDLE', 'FILE')) else 'http://proxy.invalid'
    )
    monkeypatch.setenv(name, value)
    captured = {}

    def run(command, **kwargs):
        captured.update(kwargs)
        assert command == ['auditor']
        return _completed()

    monkeypatch.setattr(audit.subprocess, 'run', run)
    assert audit._run(['auditor'], root=tmp_path, input_text='locked requirements').returncode == 0
    assert captured['env'][name] == value
    assert captured['env'] is not os.environ
    assert captured['cwd'] == tmp_path
    assert captured['env']['UV_PROJECT_ENVIRONMENT'] == str(tmp_path / '.local/python/venv')
    assert captured['input'] == 'locked requirements'
    assert os.environ[name] == value


def test_python_dependency_audit_does_not_invent_proxy_configuration(monkeypatch, tmp_path) -> None:
    keys = ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY', 'https_proxy', 'http_proxy', 'all_proxy')
    for name in keys:
        monkeypatch.delenv(name, raising=False)
    captured = {}

    def run(_command, **kwargs):
        captured.update(kwargs)
        return _completed()

    monkeypatch.setattr(audit.subprocess, 'run', run)
    audit._run(['auditor'], root=tmp_path)
    assert not set(keys).intersection(captured['env'])


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


@pytest.mark.parametrize('scheme', ('http', 'https', 'socks5', 'socks5h'))
def test_proxy_failure_redacts_url_credentials(scheme) -> None:
    process = _completed(
        1,
        stderr=(
            f'requests.exceptions.ProxyError: {scheme}://fixture-user:fixture-pass@proxy.invalid'
        ),
    )

    result = audit._failure('pip-audit', process)
    message = result.diagnostics[0].message

    assert result.status.value == 'FAIL'
    assert result.reason == 'network-unavailable'
    assert f'{scheme}://<redacted>@proxy.invalid' in message
    assert 'fixture-user' not in message
    assert 'fixture-pass' not in message
