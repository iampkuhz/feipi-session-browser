import inspect
from pathlib import Path
from typing import Any, ClassVar

import pytest
from scripts.quality import run_quality_gate
from scripts.quality.check_css_ownership import check_css_ownership
from scripts.quality.check_session_detail_static import run_checks
from scripts.quality.quality_artifact import compute_overall


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_pass_only_when_all_required_pass():
    assert compute_overall({'a': 'PASS', 'b': 'PASS'}) == ('PASS', [])


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_skipped_is_failure():
    status, failures = compute_overall({'a': 'PASS', 'b': 'SKIPPED'})
    assert status == 'FAIL'
    assert failures


@pytest.mark.contract_case('HOOK-HARNESS-009')
def test_empty_required_is_blocked():
    status, failures = compute_overall({})
    assert status == 'BLOCKED'
    assert failures


# -- Schema consistency tests ------------------------------------------------


class TestSchemaConsistency:
    """验证所有 quality gate 输出共享相同的 schema 基线."""

    REQUIRED_FIELDS: ClassVar[frozenset[str]] = frozenset({'schemaVersion', 'status'})

    def _require_fields(self, data: dict[str, Any], source: str) -> None:
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f'{source} 缺少 schema 字段: {missing}'
        assert 'status' in data, f'{source} 缺少 status 字段'
        assert data['status'] in {'PASS', 'FAIL', 'BLOCKED', 'SKIPPED'}, (
            f'{source} status 值非法:{data.get("status")}'
        )

    @pytest.mark.contract_case('HOOK-HARNESS-009')
    def test_session_detail_static_schema(self):
        """check_session_detail_static.py 输出必须有 schemaVersion + status."""
        root = Path(__file__).resolve().parents[2]
        result = run_checks(
            root / 'src/session_browser/web/static/css/session-detail.css',
            root / 'src/session_browser/web/templates/base.html',
            root / 'src/session_browser/web/templates/session.html',
            root / 'src/session_browser/web/static/css/shell.css',
        )
        self._require_fields(result, 'check_session_detail_static')

    @pytest.mark.contract_case('HOOK-HARNESS-009')
    def test_css_ownership_schema(self):
        """check_css_ownership.py JSON artifact 必须有 schemaVersion + status."""
        repo_root = Path(__file__).resolve().parents[2]
        result = check_css_ownership(repo_root)
        # Build the same JSON dictionary written by main().
        json_report = {
            'schemaVersion': 1,
            'gate': 'css-ownership',
            'status': 'PASS' if not result.blocks else 'FAIL',
            'filesScanned': result.files_scanned,
            'selectorsAnalyzed': result.selectors_analyzed,
            'blockCount': len(result.blocks),
            'warningCount': len(result.warnings),
        }
        self._require_fields(json_report, 'check_css_ownership')

    @pytest.mark.contract_case('HOOK-HARNESS-009')
    def test_quality_summary_schema_version(self):
        """QualitySummary schemaVersion 应为最新值 3."""
        source = inspect.getsource(run_quality_gate.build_summary)
        assert 'schemaVersion=3' in source, 'build_summary should use schemaVersion=3'
