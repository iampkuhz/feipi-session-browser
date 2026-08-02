"""Session Browser 测试共享 pytest fixtures。"""

import os
import sys

import pytest

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKIP_REPORTS_ATTR = '_session_browser_forbidden_skip_reports'
_PYTEST_CONFIG = None


@pytest.fixture(autouse=True)
def _isolate_feipi_env(monkeypatch):
    """统一清除 Gate 身份变量，防止本机环境泄漏到任一测试目录。"""
    for variable in ('FEIPI_SESSION_ID', 'FEIPI_AGENT_CLIENT', 'FEIPI_AGENT_ID'):
        monkeypatch.delenv(variable, raising=False)


def pytest_configure(config):
    """Track skipped pytest reports so selected/full runs cannot pass with skips."""
    global _PYTEST_CONFIG
    _PYTEST_CONFIG = config
    setattr(config, _SKIP_REPORTS_ATTR, [])


def _record_forbidden_skip(config, report) -> None:
    if not getattr(report, 'skipped', False):
        return
    reports = getattr(config, _SKIP_REPORTS_ATTR, None)
    if reports is None:
        reports = []
        setattr(config, _SKIP_REPORTS_ATTR, reports)
    location = getattr(report, 'location', None)
    if location:
        file_name, line_no, _test_name = location
        loc = f'{file_name}:{line_no + 1}'
    else:
        loc = getattr(report, 'nodeid', '<unknown>')
    reports.append(
        {
            'nodeid': getattr(report, 'nodeid', '<unknown>'),
            'when': getattr(report, 'when', 'collect'),
            'location': loc,
        }
    )


def pytest_runtest_logreport(report):
    config = getattr(report, 'config', None) or _PYTEST_CONFIG
    if config is not None:
        _record_forbidden_skip(config, report)


def pytest_collectreport(report):
    config = getattr(report, 'config', None) or _PYTEST_CONFIG
    if config is not None:
        _record_forbidden_skip(config, report)


def pytest_sessionfinish(session, exitstatus):
    _ = exitstatus  # Pytest hook 签名要求保留该参数；最终状态统一写回 session。
    reports = getattr(session.config, _SKIP_REPORTS_ATTR, [])
    if not reports:
        return
    terminal = session.config.pluginmanager.get_plugin('terminalreporter')
    lines = [
        'pytest skipped outcomes are forbidden. Use deterministic fixtures, explicit assertions, or target mapping instead.',
        f'forbidden skipped reports: {len(reports)}',
    ]
    for item in reports[:20]:
        lines.append(f' - {item["nodeid"]} [{item["when"]}] at {item["location"]}')
    if len(reports) > 20:
        lines.append(f' - ... {len(reports) - 20} more')
    if terminal:
        terminal.write_sep('=', 'no test skips enforcement')
        for line in lines:
            terminal.write_line(line)
    else:
        print('\n'.join(lines), file=sys.stderr)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
