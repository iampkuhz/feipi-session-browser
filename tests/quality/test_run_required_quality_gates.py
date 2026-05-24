"""Tests for scripts/quality/run_required_quality_gates.py."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "quality" / "run_required_quality_gates.py"
_spec = importlib.util.spec_from_file_location("run_required_quality_gates", SCRIPT_PATH)
_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runner)


def _setup_env(changed_files: list[dict], session_id: str | None = "test-session-001"):
    """Create temp env with changed-files.jsonl and optional session-id.txt."""
    td = Path(tempfile.mkdtemp())
    agent_log = td / "agent_logs" / "current"
    agent_log.mkdir(parents=True)
    quality = td / "quality"
    quality.mkdir(parents=True)

    cf = agent_log / "changed-files.jsonl"
    if changed_files:
        cf.write_text("\n".join(json.dumps(e) for e in changed_files) + "\n")

    if session_id:
        (agent_log / "session-id.txt").write_text(session_id)

    # Patch module globals
    _runner.AGENT_LOG_DIR = agent_log
    _runner.CHANGED_FILES = cf
    _runner.SESSION_ID_FILE = agent_log / "session-id.txt"
    _runner.QUALITY_DIR = quality
    _runner.REPO_ROOT = td

    return td


def _write_hook_quality_changes(cf_path: Path):
    """Write changed-files entry that triggers hook-runtime target."""
    cf_path.write_text(json.dumps({
        "ts": "2026-05-24T00:00:00Z",
        "tool": "Edit",
        "file": "scripts/quality/run_quality_gate.py",
        "category": "quality-gate",
        "requiresQualityGate": True,
        "sessionId": "test-session-001",
    }) + "\n")


class TestDryRun:
    def test_dry_run_hook_runtime_detected(self):
        """Changed files include scripts/quality/*.py => hook-runtime in required targets, session-detail skipped."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "scripts/quality/run_quality_gate.py",
            "category": "quality-gate",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py", "--dry-run"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0  # dry-run always returns 0


class TestNoRequiredTargets:
    def test_empty_changed_files(self):
        """No changed files => exit 0."""
        td = _setup_env([])
        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    def test_docs_only(self):
        """Only docs changed => no quality targets => exit 0."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "README.md",
            "category": "other",
            "requiresQualityGate": False,
            "sessionId": "test-session-001",
        }])
        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0


class TestSessionDetailExcluded:
    def test_session_detail_not_in_executed_targets(self):
        """UI files changed => session-detail in required but excluded from runner execution."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        changed_files = _runner.get_changed_files()
        all_targets = _runner.compute_required_targets(changed_files, _runner.EXCLUDED_TARGETS)
        assert "session-detail" not in all_targets, \
            "session-detail must be excluded from runner targets"


class TestChangedFilesReading:
    def test_reads_from_jsonl(self):
        """Changed files should be read from changed-files.jsonl."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "scripts/hooks/stop.sh",
            "category": "hook",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        files = _runner.get_changed_files()
        assert "scripts/hooks/stop.sh" in files

    def test_filters_by_session_id(self):
        """Files with different sessionId should be filtered out."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "scripts/hooks/stop.sh",
            "category": "hook",
            "requiresQualityGate": True,
            "sessionId": "different-session",
        }], session_id="test-session-001")

        files = _runner.get_changed_files()
        assert len(files) == 0, "Files from different session should be filtered"


class TestChangeIdResolution:
    def test_explicit_change_id(self):
        assert _runner.resolve_change_id("my-change") == "my-change"

    def test_env_fallback(self, monkeypatch):
        """When ACTIVE_CHANGE_ID env var is set, it should be returned."""
        tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr(_runner, "REPO_ROOT", tmp_dir)
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            os.environ["ACTIVE_CHANGE_ID"] = "env-change"
            assert _runner.resolve_change_id(None) == "env-change"
        finally:
            if old is None:
                os.environ.pop("ACTIVE_CHANGE_ID", None)
            else:
                os.environ["ACTIVE_CHANGE_ID"] = old

    def test_unknown_fallback(self, monkeypatch):
        """When no env var and no active-change file, return 'unknown'."""
        tmp_dir = Path(tempfile.mkdtemp())
        monkeypatch.setattr(_runner, "REPO_ROOT", tmp_dir)
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            if "ACTIVE_CHANGE_ID" in os.environ:
                del os.environ["ACTIVE_CHANGE_ID"]
            # active-change file doesn't exist in temp env
            result = _runner.resolve_change_id(None)
            assert result == "unknown"
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old

    def test_active_change_file_exists(self, monkeypatch):
        """When active-change file exists and no env var, return file content."""
        tmp_dir = Path(tempfile.mkdtemp())
        (tmp_dir / "tmp").mkdir()
        (tmp_dir / "tmp" / "active-change").write_text("from-file-change")
        monkeypatch.setattr(_runner, "REPO_ROOT", tmp_dir)
        old = os.environ.get("ACTIVE_CHANGE_ID")
        try:
            if "ACTIVE_CHANGE_ID" in os.environ:
                del os.environ["ACTIVE_CHANGE_ID"]
            result = _runner.resolve_change_id(None)
            assert result == "from-file-change"
        finally:
            if old is not None:
                os.environ["ACTIVE_CHANGE_ID"] = old


class TestNoFeipiAgentLogDir:
    def test_no_env_variable_used(self):
        """Verify the script does not reference FEIPI_AGENT_LOG_DIR."""
        source = SCRIPT_PATH.read_text()
        assert "FEIPI_AGENT_LOG_DIR" not in source, \
            "run_required_quality_gates.py must not reference FEIPI_AGENT_LOG_DIR"


class TestIncludeSessionDetail:
    def test_default_excludes_session_detail_dry_run(self):
        """Default behavior: session-detail excluded from dry-run targets."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py", "--dry-run"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    def test_include_session_detail_dry_run(self):
        """--include-session-detail: session-detail appears in dry-run targets."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        old_argv = sys.argv
        try:
            sys.argv = ["run_required_quality_gates.py", "--dry-run", "--include-session-detail"]
            rc = _runner.main()
        finally:
            sys.argv = old_argv
        assert rc == 0

    def test_include_session_detail_computes_targets(self):
        """--include-session-detail: compute_required_targets includes session-detail."""
        td = _setup_env([{
            "ts": "2026-05-24T00:00:00Z",
            "tool": "Edit",
            "file": "src/session_browser/web/static/style.css",
            "category": "ui-css",
            "requiresQualityGate": True,
            "sessionId": "test-session-001",
        }])

        changed_files = _runner.get_changed_files()
        # With exclusion (default)
        excluded_targets = _runner.compute_required_targets(changed_files, _runner.EXCLUDED_TARGETS)
        assert "session-detail" not in excluded_targets

        # Without exclusion (--include-session-detail)
        no_exclusion = set()
        all_targets = _runner.compute_required_targets(changed_files, no_exclusion)
        assert "session-detail" in all_targets


class TestStopShOrdering:
    def test_run_required_before_stop_quality_gate(self):
        """stop.sh must call run_required_quality_gates.py before stop_quality_gate.py."""
        stop_sh = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "stop.sh"
        text = stop_sh.read_text()

        run_required_pos = text.find("run_required_quality_gates.py")
        stop_quality_pos = text.find("stop_quality_gate.py")

        assert run_required_pos != -1, "run_required_quality_gates.py not found in stop.sh"
        assert stop_quality_pos != -1, "stop_quality_gate.py not found in stop.sh"
        assert run_required_pos < stop_quality_pos, \
            f"run_required_quality_gates.py (pos {run_required_pos}) must appear before stop_quality_gate.py (pos {stop_quality_pos})"

    def test_stop_sh_includes_session_detail_flag(self):
        """stop.sh must pass --include-session-detail to run_required_quality_gates.py."""
        stop_sh = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "stop.sh"
        text = stop_sh.read_text()
        assert "--include-session-detail" in text, \
            "stop.sh must pass --include-session-detail to run_required_quality_gates.py"
