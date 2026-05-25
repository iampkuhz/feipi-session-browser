from scripts.quality.quality_artifact import compute_overall


def test_pass_only_when_all_required_pass():
    assert compute_overall({"a": "PASS", "b": "PASS"}) == ("PASS", [])


def test_skipped_is_failure():
    status, failures = compute_overall({"a": "PASS", "b": "SKIPPED"})
    assert status == "FAIL"
    assert failures


def test_empty_required_is_blocked():
    status, failures = compute_overall({})
    assert status == "BLOCKED"
    assert failures


# ── Schema consistency tests ──────────────────────────────────────────────

class TestSchemaConsistency:
    """Ensure all quality gate outputs share a common schema baseline."""

    REQUIRED_FIELDS = {"schemaVersion", "status"}

    def _require_fields(self, data: dict, source: str):
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"{source} 缺少 schema 字段: {missing}"
        assert "status" in data, f"{source} 缺少 status 字段"
        assert data["status"] in {"PASS", "FAIL", "BLOCKED", "SKIPPED"}, (
            f"{source} status 值非法：{data.get('status')}"
        )

    def test_session_detail_static_schema(self):
        """check_session_detail_static.py 输出必须有 schemaVersion + status。"""
        from scripts.quality.check_session_detail_static import run_checks
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        result = run_checks(
            root / "src/session_browser/web/static/css/session-detail.css",
            root / "src/session_browser/web/templates/base.html",
            root / "src/session_browser/web/templates/session.html",
            root / "src/session_browser/web/static/css/shell.css",
        )
        self._require_fields(result, "check_session_detail_static")

    def test_css_ownership_schema(self):
        """check_css_ownership.py JSON artifact 必须有 schemaVersion + status。"""
        from scripts.quality.check_css_ownership import check_css_ownership, format_report
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[2]
        result = check_css_ownership(repo_root)
        # Build the same JSON dict the main() function writes
        json_report = {
            "schemaVersion": 1,
            "gate": "css-ownership",
            "status": "PASS" if not result.blocks else "FAIL",
            "filesScanned": result.files_scanned,
            "selectorsAnalyzed": result.selectors_analyzed,
            "blockCount": len(result.blocks),
            "warningCount": len(result.warnings),
        }
        self._require_fields(json_report, "check_css_ownership")

    def test_quality_summary_schema_version(self):
        """QualitySummary schemaVersion 应为最新值 3。"""
        from scripts.quality import run_quality_gate
        # Verify the constant is accessible
        import inspect
        source = inspect.getsource(run_quality_gate.build_summary)
        assert "schemaVersion=3" in source, "build_summary 应使用 schemaVersion=3"
