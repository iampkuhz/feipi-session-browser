from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from scripts.gates.checks.repository import check_no_python_playwright_skips as subject


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_reports_python_skip_apis(tmp_path: Path) -> None:
    _write(
        tmp_path / 'tests' / 'test_bad.py',
        'import pytest\n'
        + 'pytest.'
        + "skip('missing fixture')\n@pytest.mark."
        + "skipif(True, reason='legacy')\ndef test_case(): pass\n",
    )

    findings = subject._scan_repo(tmp_path)

    assert {finding.rule for finding in findings} == {
        'pytest-runtime-skip',
        'pytest-skip-marker',
    }


def test_reports_playwright_skip_and_fixme_apis(tmp_path: Path) -> None:
    _write(
        tmp_path / 'tests' / 'playwright' / 'bad.spec.ts',
        'test.' + "skip('case', async () => {});\n" + 'test.' + "fixme(true, 'broken');\n",
    )

    findings = subject._scan_repo(tmp_path)

    assert {finding.rule for finding in findings} == {
        'playwright-test-skip',
        'playwright-fixme',
    }


def test_does_not_scan_java_sources(tmp_path: Path) -> None:
    _write(
        tmp_path / 'tests' / 'ExampleTest.java',
        '@Disabled("not owned by this check") class ExampleTest {}\n',
    )

    assert subject._scan_repo(tmp_path) == []
