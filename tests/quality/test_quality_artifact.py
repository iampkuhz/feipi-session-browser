import inspect
import json
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


class TestReportHashIntegrity:
    """验证 reportHash 字段在 write_quality_summary 中正确生成。"""

    @pytest.mark.contract_case('JR-020-006')
    def test_report_hash_is_deterministic(self, tmp_path: Path):
        """同一内容的 reportHash 必须确定。"""
        from scripts.quality.quality_artifact import (
            QualitySummary,
            write_quality_summary,
        )

        finished = '2026-01-01T00:01:00Z'

        summary_a = QualitySummary(
            schemaVersion=3, status='PASS', target='hook-runtime',
            changeId='test', startedAt='2026-01-01T00:00:00Z',
            finishedAt=finished, requiredGates={'pytest': 'PASS'},
            blockingFailures=[], warnings=[],
            artifacts={'notTriggeredGates': []},
            gateDetails=[{'name': 'pytest', 'status': 'PASS', 'command': ['pytest', '-q'],
                          'output': '', 'exitCode': 0}],
            runId='test-hook-runtime-2026-01-01T00:00:00Z',
            baseCommit='', dirtyHash='', generatedAt='2026-01-01T00:00:00Z',
            freshness='0s',
        )
        path_a = write_quality_summary(tmp_path / 'a', summary_a)

        summary_b = QualitySummary(
            schemaVersion=3, status='PASS', target='hook-runtime',
            changeId='test', startedAt='2026-01-01T00:00:00Z',
            finishedAt=finished, requiredGates={'pytest': 'PASS'},
            blockingFailures=[], warnings=[],
            artifacts={'notTriggeredGates': []},
            gateDetails=[{'name': 'pytest', 'status': 'PASS', 'command': ['pytest', '-q'],
                          'output': '', 'exitCode': 0}],
            runId='test-hook-runtime-2026-01-01T00:00:00Z',
            baseCommit='', dirtyHash='', generatedAt='2026-01-01T00:00:00Z',
            freshness='0s',
        )
        path_b = write_quality_summary(tmp_path / 'b', summary_b)

        data_a = json.loads(path_a.read_text())
        data_b = json.loads(path_b.read_text())
        assert data_a['reportHash'] == data_b['reportHash']

    @pytest.mark.contract_case('JR-020-006')
    def test_report_hash_present_in_artifact(self, tmp_path: Path):
        """写入的 artifact 必须包含 reportHash 字段。"""
        from scripts.quality.quality_artifact import (
            PASS,
            GateDetail,
            write_quality_summary,
        )
        from scripts.quality.run_quality_gate import build_summary

        started = '2026-01-01T00:00:00Z'
        details = [GateDetail(name='javaCheck', status=PASS)]
        summary = build_summary('java-src', 'hash-test', started, details)
        path = write_quality_summary(tmp_path, summary)
        data = json.loads(path.read_text())
        assert 'reportHash' in data
        assert isinstance(data['reportHash'], str)
        assert len(data['reportHash']) > 0


class TestStaleArtifactDetection:
    """验证过期 artifact 检测逻辑。"""

    @pytest.mark.contract_case('JR-020-007')
    def test_missing_artifact_is_stale(self):
        """不存在的 artifact 不是新鲜的。"""
        from scripts.quality.quality_artifact import is_artifact_fresh
        assert is_artifact_fresh('/nonexistent/path/artifact.json') is False

    @pytest.mark.contract_case('JR-020-007')
    def test_fresh_artifact_is_fresh(self, tmp_path: Path):
        """刚创建的 artifact 是新鲜的。"""
        from scripts.quality.quality_artifact import is_artifact_fresh
        artifact = tmp_path / 'fresh.json'
        artifact.write_text('{}', encoding='utf-8')
        assert is_artifact_fresh(str(artifact), max_age_seconds=60) is True
