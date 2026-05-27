"""Tests for scripts/hooks/log_file_change.py."""
import pytest
import importlib.util
import json
import os
import sys
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parents[2] / "scripts" / "hooks" / "log_file_change.py"
_spec = importlib.util.spec_from_file_location("log_file_change", HOOK_PATH)
_lfc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lfc)

_classify = _lfc._classify
_extract_file_path = _lfc._extract_file_path
_extract_tool_name = _lfc._extract_tool_name
_make_entry = _lfc._make_entry


class TestClassify:
    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_css_ui(self):
        cat, qg = _classify("src/session_browser/web/static/css/shell.css")
        assert cat == "ui-css"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_template_ui(self):
        cat, qg = _classify("src/session_browser/web/templates/session.html")
        assert cat == "ui-template"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_js_ui(self):
        cat, qg = _classify("src/session_browser/web/static/js/app.js")
        assert cat == "ui-js"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_quality_gate(self):
        cat, qg = _classify("scripts/quality/run_quality_gate.py")
        assert cat == "quality-gate"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_hook_claude(self):
        cat, qg = _classify(".claude/hooks/stop_check.sh")
        assert cat == "hook"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_hook_agent(self):
        cat, qg = _classify("scripts/agent_hooks/log_change_evidence.py")
        assert cat == "hook"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_hook_scripts(self):
        cat, qg = _classify("scripts/hooks/log_file_change.py")
        assert cat == "hook"
        assert qg is True

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_llm_command(self):
        cat, qg = _classify(".claude/commands/diagnose-ui-gate.md")
        assert cat == "llm-command"
        assert qg is False

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_quality_doc(self):
        cat, qg = _classify("harness/quality/quality-gate-matrix.md")
        assert cat == "quality-doc"
        assert qg is False

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_openspec(self):
        cat, qg = _classify("openspec/changes/foo/proposal.md")
        assert cat == "openspec"
        assert qg is False

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_other(self):
        cat, qg = _classify("README.md")
        assert cat == "other"
        assert qg is False

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_test_file(self):
        cat, qg = _classify("tests/test_something.py")
        assert cat == "test"
        assert qg is False


class TestExtractFilePath:
    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_top_level_file_path(self):
        payload = {"file_path": "src/a.css"}
        assert _extract_file_path(payload) == "src/a.css"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_top_level_path(self):
        payload = {"path": "src/b.css"}
        assert _extract_file_path(payload) == "src/b.css"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_tool_input_file_path(self):
        payload = {"tool_input": {"file_path": "src/c.css"}}
        assert _extract_file_path(payload) == "src/c.css"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_tool_input_path(self):
        payload = {"tool_input": {"path": "src/d.css"}}
        assert _extract_file_path(payload) == "src/d.css"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_tool_input_notebook_path(self):
        payload = {"tool_input": {"notebook_path": "src/notebook.ipynb"}}
        assert _extract_file_path(payload) == "src/notebook.ipynb"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_multiedit_first_file(self):
        payload = {
            "tool_input": {
                "edits": [
                    {"file_path": "src/a.css"},
                    {"file_path": "src/b.css"},
                ]
            }
        }
        assert _extract_file_path(payload) == "src/a.css"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_multiedit_with_path(self):
        payload = {
            "tool_input": {
                "edits": [
                    {"path": "src/x.css"},
                ]
            }
        }
        assert _extract_file_path(payload) == "src/x.css"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_empty_payload(self):
        assert _extract_file_path({}) is None


class TestExtractToolName:
    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_tool_name(self):
        assert _extract_tool_name({"tool_name": "Edit"}) == "Edit"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_tool(self):
        assert _extract_tool_name({"tool": "Write"}) == "Write"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_tool_name_priority(self):
        assert _extract_tool_name({"tool_name": "Edit", "tool": "Write"}) == "Edit"

    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_unknown(self):
        assert _extract_tool_name({}) == "unknown"


class TestMakeEntry:
    @pytest.mark.contract_case("HOOK-HARNESS-005")
    def test_entry_structure(self):
        entry = _make_entry("src/session_browser/web/static/css/shell.css", "Edit")
        assert "ts" in entry
        assert entry["tool"] == "Edit"
        assert entry["file"] == "src/session_browser/web/static/css/shell.css"
        assert entry["category"] == "ui-css"
        assert entry["requiresQualityGate"] is True
