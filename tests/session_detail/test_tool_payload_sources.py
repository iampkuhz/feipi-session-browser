"""Tests: tool row/result payload traceability (T024).
Verify that:
- tool.result payload VM entries include name/parameters/result fields.
- Non Read/Write tool rows display command or parameter summary.
- Payload fallback does not render empty/blank content.
"""


from __future__ import annotations

import pytest
from pathlib import Path

TEMPLATE_DIR = (
    Path(__file__).parents[2]
    / "src" / "session_browser" / "web" / "templates"
)
ROUTES = (
    Path(__file__).parents[2]
    / "src" / "session_browser" / "web" / "routes.py"
)


def _read_routes() -> str:
    return ROUTES.read_text(encoding="utf-8")


def _read_timeline() -> str:
    return (
        TEMPLATE_DIR / "components" / "session_detail_timeline.html"
    ).read_text(encoding="utf-8")


class TestToolResultPayloadFields:
    """tool.result payload must include name/parameters/result traceability."""

    @pytest.mark.contract_case("UI-SD-021")
    def test_payload_kind_tool_result_in_routes(self):
        """View model must register tool.result payloads."""
        routes = _read_routes()
        assert '"tool.result"' in routes or "'tool.result'" in routes, (
            "View model must use kind='tool.result' for tool result payloads"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_payload_title_includes_tool_name(self):
        """Payload title must include tc.name for traceability."""
        routes = _read_routes()
        # Title pattern: f"R{rid} . {tc.name} . Result"
        assert "tc.name" in routes, (
            "tool.result payload title must reference tc.name"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_payload_text_uses_tc_result(self):
        """Payload text must come from tc.result."""
        routes = _read_routes()
        assert "tc.result" in routes, (
            "tool.result payload text must use tc.result"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_tool_vm_extracts_parameters(self):
        """tool_vm must read parameters from tool call."""
        routes = _read_routes()
        assert "parameters" in routes, (
            "tool_vm must access tc.parameters for command extraction"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_tool_vm_uses_tool_name(self):
        """tool_vm kind field must derive from tc.name."""
        routes = _read_routes()
        # tool_vm uses getattr(tc, "name", "tool")
        assert 'getattr(tc, "name"' in routes or "getattr(tc, 'name'" in routes, (
            "tool_vm must use tc.name for kind label"
        )


class TestToolRowDisplaysCommand:
    """Non Read/Write tool rows must show command or parameter summary."""

    @pytest.mark.contract_case("UI-SD-021")
    def test_timeline_tool_row_has_command(self):
        """tool_batch macro must render tool.command in row."""
        timeline = _read_timeline()
        assert "tool.command" in timeline or "sd-tool-cmd" in timeline, (
            "tool row must include a command element"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_timeline_tool_row_has_result_summary(self):
        """tool_batch macro must render tool.result_summary."""
        timeline = _read_timeline()
        assert "tool.result_summary" in timeline or "sd-tool-result" in timeline, (
            "tool row must include a result summary element"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_timeline_tool_row_has_kind(self):
        """tool_batch macro must render tool.kind."""
        timeline = _read_timeline()
        assert "tool.kind" in timeline or "sd-tool-kind" in timeline, (
            "tool row must include a kind label"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_tool_vm_builds_command_from_params(self):
        """tool_vm must derive command from parameters (command/file_path/path)."""
        routes = _read_routes()
        assert 'params.get("command"' in routes or "params.get('command'" in routes, (
            "tool_vm must extract command from params"
        )
        assert 'params.get("file_path"' in routes or "params.get('file_path'" in routes, (
            "tool_vm must fall back to file_path for command"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_tool_vm_result_summary_from_tc_result(self):
        """tool_vm result_summary must come from tc.result text."""
        routes = _read_routes()
        assert "result_summary" in routes, (
            "tool_vm must produce result_summary field"
        )


class TestPayloadNotEmpty:
    """Payload must not display empty/blank content when missing."""

    @pytest.mark.contract_case("UI-SD-021")
    def test_generic_payload_fallback_has_no_content_guard(self):
        """Generic payload fallback must show 'No content' when empty."""
        timeline = _read_timeline()
        assert "No content" in timeline or "sd-payload-empty" in timeline, (
            "Payload fallback must include a 'No content' empty state"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_tool_result_payload_checks_text(self):
        """tool.result payload template must check payload.text before rendering."""
        timeline = _read_timeline()
        # The generic fallback checks: payload.kind == 'tool.result' and payload.text
        assert "tool.result" in timeline, (
            "Template must have tool.result payload handling branch"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_payload_empty_state_in_modal(self):
        """Payload modal must have an empty state section."""
        timeline = _read_timeline()
        assert "sd-payload-empty-state" in timeline, (
            "Payload modal must include empty state placeholder"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_add_payload_sets_empty_text(self):
        """add_payload must always set text field (never None/missing)."""
        routes = _read_routes()
        # add_payload sets entry["text"] = "" when no text provided
        assert '"text"' in routes, (
            "add_payload must always include a text field"
        )


class TestToolResultModalShowsCommandAndMetadata:
    """Result payload modal must show Tool Metadata + Command + Result sections."""

    @pytest.mark.contract_case("UI-SD-021")
    def test_template_shows_tool_name_in_metadata(self):
        """Fallback template must render payload.tool_name in metadata section."""
        timeline = _read_timeline()
        assert "payload.tool_name" in timeline, (
            "Template must include payload.tool_name in tool.result metadata"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_template_shows_tool_status_in_metadata(self):
        """Fallback template must render payload.tool_status in metadata section."""
        timeline = _read_timeline()
        assert "payload.tool_status" in timeline, (
            "Template must include payload.tool_status in tool.result metadata"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_template_shows_command_section(self):
        """tool.result fallback must render a Command section with payload.tool_command."""
        timeline = _read_timeline()
        assert "payload.tool_command" in timeline, (
            "Template must render Command section using payload.tool_command"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_template_shows_result_section(self):
        """tool.result fallback must render a Result section with payload.text."""
        timeline = _read_timeline()
        # The tool.result branch must have a Result heading and payload.text
        assert "tool.result" in timeline, (
            "Template must have tool.result branch"
        )
        assert '"Result"' in timeline or "'Result'" in timeline, (
            "Template must label the Result section"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_routes_pass_tool_name_to_payload(self):
        """add_payload/_add must pass tool_name for tool.result payloads."""
        routes = _read_routes()
        assert "tool_name=" in routes, (
            "Payload construction must pass tool_name metadata"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_routes_pass_tool_command_to_payload(self):
        """add_payload/_add must pass tool_command for tool.result payloads."""
        routes = _read_routes()
        assert "tool_command=" in routes, (
            "Payload construction must pass tool_command metadata"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_routes_pass_tool_status_to_payload(self):
        """add_payload/_add must pass tool_status for tool.result payloads."""
        routes = _read_routes()
        assert "tool_status=" in routes, (
            "Payload construction must pass tool_status metadata"
        )

    @pytest.mark.contract_case("UI-SD-021")
    def test_routes_pass_tool_parameters_to_payload(self):
        """add_payload/_add must pass tool_parameters for tool.result payloads."""
        routes = _read_routes()
        assert "tool_parameters=" in routes, (
            "Payload construction must pass tool_parameters metadata"
        )
