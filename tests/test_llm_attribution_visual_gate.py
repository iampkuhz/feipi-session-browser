"""Behavior tests for the LLM attribution visual gate script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract_case('HOOK-HARNESS-008')

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / 'scripts'
    / 'quality'
    / 'run_llm_attribution_visual_gate.py'
)


@pytest.fixture(scope='module')
def gate_module():
    spec = importlib.util.spec_from_file_location('run_llm_attribution_visual_gate', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_gate_cli(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_help_exposes_required_cli_options():
    result = _run_gate_cli('--help', timeout=10)

    assert result.returncode == 0
    help_text = result.stdout + result.stderr
    assert '--url' in help_text
    assert '--url-file' in help_text
    assert '--out' in help_text
    assert '--self-test' in help_text


def test_self_test_covers_internal_contracts():
    result = _run_gate_cli('--self-test', timeout=30)

    assert result.returncode == 0, result.stderr
    assert 'All self-tests passed' in result.stdout


def test_default_output_path_uses_test_results(gate_module):
    assert (
        Path(__file__).resolve().parent.parent
        / 'test-results'
        / 'quality'
        / 'llm-attribution-visual'
    ) == gate_module.DEFAULT_OUT


def test_missing_url_writes_blocked_result_and_report(tmp_path: Path):
    result = _run_gate_cli('--out', str(tmp_path), timeout=30)

    assert result.returncode == 2
    assert 'No --url provided' in result.stderr

    result_json = tmp_path / 'result.json'
    report_md = tmp_path / 'report.md'
    assert result_json.exists()
    assert report_md.exists()

    data = json.loads(result_json.read_text(encoding='utf-8'))
    assert data['status'] == 'BLOCKED'
    assert data['gate'] == 'llm-attribution-visual'
    assert data['viewports'] == ['1440x900', '2560x1440']
    assert data['summary']['blocked'] == 1
    assert data['diagnostics'][0]['code'] == 'NO_URL'
    assert 'LLM Attribution Visual Gate Report' in report_md.read_text(encoding='utf-8')


@pytest.mark.parametrize(
    ('url_file_content', 'expected_code'),
    [
        ('', 'URL_FILE_EMPTY'),
        ('# comment only\n\n', 'URL_FILE_EMPTY'),
        ('not-a-url\n', 'URL_FILE_INVALID'),
        ('http://example.com/a\nhttp://example.com/b\n', 'URL_FILE_MULTI'),
    ],
)
def test_url_file_validation_blocks_without_browser(
    tmp_path: Path,
    url_file_content: str,
    expected_code: str,
):
    url_file = tmp_path / 'url.txt'
    out_dir = tmp_path / 'out'
    url_file.write_text(url_file_content, encoding='utf-8')

    result = _run_gate_cli('--url-file', str(url_file), '--out', str(out_dir), timeout=30)

    assert result.returncode == 2
    data = json.loads((out_dir / 'result.json').read_text(encoding='utf-8'))
    assert data['status'] == 'BLOCKED'
    assert data['diagnostics'][0]['code'] == expected_code


def test_url_file_missing_blocks_without_browser(tmp_path: Path):
    out_dir = tmp_path / 'out'

    result = _run_gate_cli(
        '--url-file',
        str(tmp_path / 'does-not-exist.txt'),
        '--out',
        str(out_dir),
        timeout=30,
    )

    assert result.returncode == 2
    data = json.loads((out_dir / 'result.json').read_text(encoding='utf-8'))
    assert data['status'] == 'BLOCKED'
    assert data['diagnostics'][0]['code'] == 'URL_FILE_NOT_FOUND'


def test_request_text_contract_rejects_raw_payload_labels(gate_module):
    text = '基于本地日志重建，不等同于真实 provider request/response body。raw request'

    result = gate_module._check_request_text(text)

    assert result['status'] == 'FAIL'
    assert 'hasNoRawRequest' in result['failed']


def test_response_text_contract_allows_missing_display_only_section(gate_module):
    text = (
        '基于本地日志重建，不等同于真实 provider request/response body。'
        '用量分布 归因明细 Blocks 明细 可见内容摘要 参数可得性表'
    )

    result = gate_module._check_response_text(text, has_display_only=False)

    assert result['status'] == 'PASS'
    assert result['hasExclusionLabel'] is True
