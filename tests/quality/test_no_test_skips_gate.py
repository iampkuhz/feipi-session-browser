"""Tests for the no-test-skips quality gate and pytest runtime enforcement."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.quality import check_no_test_skips
from tests import conftest as test_conftest


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_scanner_reports_pytest_runtime_and_marker_skips(tmp_path: Path):
    bad_runtime = 'pytest.' + 'skip('
    bad_marker = 'pytest.mark.' + 'skipif'
    _write(
        tmp_path / 'tests' / 'test_bad.py',
        'import pytest\n'
        f"def test_runtime():\n    {bad_runtime}'missing fixture')\n"
        f"@{bad_marker}(True, reason='legacy')\n"
        'def test_marker():\n    assert True\n',
    )

    findings = check_no_test_skips.scan_repo(tmp_path)

    assert {finding.rule for finding in findings} == {
        'pytest-runtime-skip',
        'pytest-skip-marker',
    }


def test_scanner_reports_playwright_skip_and_fixme(tmp_path: Path):
    bad_skip = 'test.' + 'skip('
    bad_describe = 'test.describe.' + 'skip'
    bad_fixme = 'test.' + 'fixme('
    _write(
        tmp_path / 'tests' / 'playwright' / 'bad.spec.js',
        "const { test } = require('@playwright/test');\n"
        f"{bad_skip}'legacy path', async () => {{}});\n"
        f"{bad_describe}('group', () => {{}});\n"
        f"test('case', async () => {{ {bad_fixme}true, 'broken'); }});\n",
    )

    findings = check_no_test_skips.scan_repo(tmp_path)

    assert {finding.rule for finding in findings} == {
        'playwright-test-skip',
        'playwright-describe-skip',
        'playwright-fixme',
    }


def test_scanner_passes_for_repo_sources():
    findings = check_no_test_skips.scan_repo()

    assert findings == []


def test_gradle_java_xml_checker_fails_closed_for_missing_or_empty_reports():
    build_script = Path('build.gradle.kts').read_text(encoding='utf-8')

    assert 'Missing Java test result XML for module(s) with test sources' in build_script
    assert 'Found 0 Java tests in $filesFound test result XML file(s).' in build_script
    assert 'hasTestSources && moduleFilesFound == 0' in build_script


def test_gradle_java_xml_checker_rejects_failure_error_skip_and_abort():
    build_script = Path('build.gradle.kts').read_text(encoding='utf-8')

    assert 'failuresMatch = Regex("""failures="(\\d+)"""")' in build_script
    assert 'Found $totalFailures failed Java test(s).' in build_script
    assert 'Found $totalErrors errored Java test(s).' in build_script
    assert 'Found $totalSkipped skipped test(s).' in build_script
    assert '(?i)(aborted|TestAborted)' in build_script
    assert 'Found $totalAborted aborted Java test result XML file(s).' in build_script


def test_pytest_runtime_skip_enforcement_fails_session(monkeypatch: pytest.MonkeyPatch):
    config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda _name: None))
    setattr(config, test_conftest._SKIP_REPORTS_ATTR, [])
    monkeypatch.setattr(test_conftest, '_PYTEST_CONFIG', config)
    session = SimpleNamespace(config=config, exitstatus=0)
    report = SimpleNamespace(
        skipped=True,
        nodeid='tests/example/test_case.py::test_runtime_condition',
        when='call',
        location=('tests/example/test_case.py', 12, 'test_runtime_condition'),
    )

    test_conftest.pytest_runtest_logreport(report)
    test_conftest.pytest_sessionfinish(session, 0)

    assert session.exitstatus == pytest.ExitCode.TESTS_FAILED


def test_playwright_no_skip_reporter_is_configured():
    config_text = Path('playwright.config.js').read_text(encoding='utf-8')

    assert './tests/playwright/no-skip-reporter.js' in config_text


def test_playwright_no_skip_reporter_fails_skipped_results():
    script = r"""
const Reporter = require('./tests/playwright/no-skip-reporter.js');
const reporter = new Reporter();
reporter.onTestEnd({ titlePath: () => ['suite', 'case'] }, { status: 'skipped' });
Promise.resolve(reporter.onEnd({ status: 'passed' })).then((result) => {
  if (!result || result.status !== 'failed') {
    console.error(`unexpected result: ${JSON.stringify(result)}`);
    process.exit(1);
  }
});
"""
    proc = subprocess.run(
        ['node', '-e', script],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
