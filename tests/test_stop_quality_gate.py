"""Tests for scripts/hooks/stop_quality_gate.py."""
import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "stop_quality_gate.py"
_spec = importlib.util.spec_from_file_location("stop_quality_gate", SCRIPT_PATH)
_sqg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sqg)


def _make_artifact(status: str, finished: str = "2026-05-18T00:01:00Z") -> dict:
    return {
        "schemaVersion": 1,
        "status": status,
        "target": "session-detail",
        "changeId": "test",
        "startedAt": "2026-05-18T00:00:00Z",
        "finishedAt": finished,
        "requiredGates": {},
        "blockingFailures": [],
        "warnings": [],
        "artifacts": {},
    }


def _setup_env(changed_files_content: list[dict], artifact: dict | None = None, change_id: str = "test"):
    """Create a temp environment with changed-files and optional artifact."""
    td = tempfile.mkdtemp()
    p = Path(td)
    cf = p / "changed-files.jsonl"
    qd = p / "quality" / change_id
    if changed_files_content:
        cf.write_text("\n".join(json.dumps(e) for e in changed_files_content) + "\n")
    if artifact is not None:
        qd.mkdir(parents=True, exist_ok=True)
        (qd / "quality-gate-summary.json").write_text(json.dumps(artifact))

    # Patch module globals
    _sqg.CHANGED_FILES = cf
    _sqg.QUALITY_DIR = p / "quality"
    return p


class TestNoChangedFiles:
    def test_no_files_pass(self):
        _setup_env([])
        status, msgs = _sqg.run_check("test")
        assert status == "PASS"


class TestUiChanges:
    def test_missing_artifact_fails(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css", "requiresQualityGate": True,
        }])
        status, msgs = _sqg.run_check("test")
        assert status == "FAIL"
        assert any("missing" in m.lower() for m in msgs)

    def test_artifact_fail_fails(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=_make_artifact("FAIL"))
        status, msgs = _sqg.run_check("test")
        assert status == "FAIL"

    def test_artifact_stale_fails(self):
        _setup_env([{
            "ts": "2026-05-18T00:02:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=_make_artifact("PASS", finished="2026-05-18T00:01:00Z"))
        status, msgs = _sqg.run_check("test")
        assert status == "FAIL"

    def test_artifact_fresh_passes(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css", "requiresQualityGate": True,
        }], artifact=_make_artifact("PASS", finished="2026-05-18T00:01:00Z"))
        status, msgs = _sqg.run_check("test")
        assert status == "PASS"


class TestDocsOnly:
    def test_non_ui_passes(self):
        _setup_env([{
            "ts": "2026-05-18T00:00:00Z", "tool": "Edit",
            "file": "README.md",
            "category": "other", "requiresQualityGate": False,
        }])
        status, msgs = _sqg.run_check("test")
        assert status == "PASS"
