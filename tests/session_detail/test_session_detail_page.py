"""Page-specific pytest for session detail structure and contracts.

Covers:
- Hero area structure (agent pill, KPIs, summary strip)
- Tab navigation (Trace/Metrics/Payloads)
- Trace table structure (round-row + expanded-row pattern)
- Filter buttons (status-all, status-failed, collapse-all)
- Token bar 4-segment structure (fresh/read/write/out)
- Payload modal data attributes

Tests run against static templates (no server required).
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"
SESSION_HTML = TEMPLATE_DIR / "session.html"
TIMELINE_HTML = COMPONENTS / "session_detail_timeline.html"
PRIMITIVES_HTML = COMPONENTS / "session_detail_primitives.html"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        pytest.skip(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


# ── Hero area ────────────────────────────────────────────────────────


class TestHeroArea:
    """Hero area must have agent pill, KPIs, and summary strip."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read(TIMELINE_HTML)

    def test_hero_section_exists(self, timeline):
        """Hero section must use .sd-hero with data-session-overview-hero."""
        assert 'class="sd-hero"' in timeline, "Missing .sd-hero class"
        assert "data-session-overview-hero" in timeline, \
            "Hero missing data-session-overview-hero"

    def test_agent_pill_exists(self, timeline):
        """Hero must render agent pill."""
        assert "sd-agent-pill" in timeline, "Missing sd-agent-pill in hero"
        assert "summary.agent_label" in timeline, \
            "Hero must render summary.agent_label"

    def test_hero_title_exists(self, timeline):
        """Hero must have h1 title with summary.title."""
        assert "<h1" in timeline, "Missing h1 title in hero"
        assert "summary.title" in timeline, \
            "Hero title must use summary.title"

    def test_hero_meta_chips(self, timeline):
        """Hero must show model, project, date chips (short-id moved to breadcrumb)."""
        assert "summary.model" in timeline, "Missing model chip in hero"
        assert "summary.project_name" in timeline, \
            "Missing project chip in hero"
        assert "summary.date" in timeline, "Missing date chip in hero"

    def test_kpi_container_exists(self, timeline):
        """KPI container must use .sd-kpis."""
        assert 'class="sd-kpis"' in timeline, "Missing .sd-kpis container"

    def test_kpi_tokens(self, timeline):
        """KPIs must include Tokens."""
        assert "sd-kpi" in timeline, "Missing .sd-kpi items"
        # Find the tokens KPI block
        assert "Tokens" in timeline, "Missing Tokens KPI label"
        assert "metrics.tokens" in timeline, \
            "KPI must render metrics.tokens value"

    def test_kpi_rounds(self, timeline):
        """KPIs must include Rounds."""
        assert "Rounds" in timeline, "Missing Rounds KPI label"
        assert "metrics.rounds" in timeline, \
            "KPI must render metrics.rounds value"

    def test_kpi_tools(self, timeline):
        """KPIs must include Tools."""
        assert "Tools" in timeline, "Missing Tools KPI label"
        assert "metrics.tools" in timeline, \
            "KPI must render metrics.tools value"

    def test_kpi_failed(self, timeline):
        """KPIs must include Failed."""
        assert "Failed" in timeline, "Missing Failed KPI label"
        assert "metrics.failed" in timeline, \
            "KPI must render metrics.failed value"

    def test_summary_strip_exists(self, timeline):
        """Summary strip must exist with data-summary-strip."""
        assert "data-summary-strip" in timeline, \
            "Missing data-summary-strip"
        assert "sd-summary-strip" in timeline, \
            "Missing .sd-summary-strip"

    def test_summary_strip_items(self, timeline):
        """Summary strip must have status, manual input, subagents, cache write."""
        assert "sd-summary-item" in timeline, "Missing .sd-summary-item"
        assert "status_label" in timeline, "Missing status in summary strip"
        assert "manual_input_count" in timeline, \
            "Missing manual input count in summary strip"
        assert "subagent_count" in timeline, \
            "Missing subagent count in summary strip"
        assert "cache_write_pct" in timeline, \
            "Missing cache write pct in summary strip"

    def test_issue_strip_in_hero(self, timeline):
        """Issue strip must be within hero section."""
        assert "data-issue-strip" in timeline, \
            "Missing data-issue-strip in hero"
        assert "sd-issue-strip" in timeline, \
            "Missing .sd-issue-strip"

    def test_issue_strip_has_jump_action(self, timeline):
        """Issue links must use jump-round action."""
        assert 'data-action="jump-round"' in timeline, \
            "Issue links missing data-action=\"jump-round\""
        assert "data-round=" in timeline, \
            "Issue links missing data-round attribute"


# ── Tab navigation ───────────────────────────────────────────────────


class TestTabNavigation:
    """Tab navigation must have Trace, Metrics, Payloads tabs."""

    @pytest.fixture(scope="class")
    def session(self):
        return _read(SESSION_HTML)

    def test_tab_container_exists(self, session):
        """Tab nav must use .sd-tabs with data-session-tabs."""
        assert 'class="sd-tabs"' in session, "Missing .sd-tabs container"
        assert "data-session-tabs" in session, \
            "Missing data-session-tabs attribute"

    def test_trace_tab_exists(self, session):
        """Trace tab must exist with data-action=\"tab-trace\"."""
        assert 'data-action="tab-trace"' in session, \
            "Missing Trace tab"
        assert 'data-tab="trace"' in session, \
            "Missing data-tab=\"trace\""

    def test_metrics_tab_exists(self, session):
        """Metrics tab must exist with data-action=\"tab-metrics\"."""
        assert 'data-action="tab-metrics"' in session, \
            "Missing Metrics tab"
        assert 'data-tab="metrics"' in session, \
            "Missing data-tab=\"metrics\""

    def test_payloads_tab_exists(self, session):
        """Payloads tab must exist with data-action=\"tab-payloads\"."""
        assert 'data-action="tab-payloads"' in session, \
            "Missing Payloads tab"
        assert 'data-tab="payloads"' in session, \
            "Missing data-tab=\"payloads\""

    def test_trace_tab_is_active(self, session):
        """Trace tab should be the default active tab (is-active class)."""
        # The first tab (Trace) should have is-active
        tabs_section = session[
            session.find('data-session-tabs'):
            session.find('data-session-tabs') + 500
        ]
        assert "is-active" in tabs_section, \
            "No active tab found"
        # Trace tab should be active
        assert 'data-action="tab-trace"' in tabs_section.split("is-active")[0] + tabs_section.split("is-active")[1][:200], \
            "Trace tab should be active by default"

    def test_tab_aria_label(self, session):
        """Tab nav must have accessible aria-label."""
        assert 'aria-label="Session view tabs"' in session, \
            "Tab nav missing aria-label"


# ── Trace table structure ────────────────────────────────────────────


class TestTraceTableStructure:
    """Trace table must use round-row + expanded-row <tr> pattern."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read(TIMELINE_HTML)

    @pytest.fixture(scope="class")
    def session(self):
        return _read(SESSION_HTML)

    def test_trace_table_element(self, session):
        """session.html must have <table class=\"trace-table\">."""
        assert 'class="trace-table"' in session, \
            "Missing <table class=\"trace-table\">"

    def test_trace_table_data_attr(self, session):
        """Trace table must have data-trace-list."""
        assert "data-trace-list" in session, \
            "Missing data-trace-list on table"

    def test_colgroup_structure(self, session):
        """Table must have colgroup with expected columns."""
        assert "<colgroup>" in session, "Missing <colgroup>"
        assert "col-round" in session, "Missing col-round"
        assert "col-summary" in session, "Missing col-summary"
        assert "col-metrics" in session, "Missing col-metrics"
        assert "col-status" in session, "Missing col-status"

    def test_thead_structure(self, session):
        """Table must have <thead> with column headers."""
        assert "<thead>" in session, "Missing <thead>"
        assert "round-col" in session, "Missing round column header"
        assert "metrics-col" in session, "Missing metrics column header"
        assert "status-col" in session, "Missing status column header"

    def test_round_row_is_tr(self, timeline):
        """round_row macro must render <tr class=\"round-row\">."""
        pattern = re.compile(
            r'<tr\b[^>]*class="[^"]*round-row[^"]*"'
        )
        assert pattern.search(timeline), \
            "round_row must render <tr class=\"round-row\">"

    def test_round_row_data_attrs(self, timeline):
        """round-row must have data-trace-round-row, data-round, data-status."""
        assert "data-trace-round-row" in timeline, \
            "Missing data-trace-round-row"
        pattern = re.compile(r'data-round="\{\{\s*row\.round_id\s*\}\}"')
        assert pattern.search(timeline), \
            "Missing data-round template attribute"
        assert 'data-status="' in timeline, \
            "Missing data-status on round-row"

    def test_expanded_row_is_tr(self, timeline):
        """expanded_row macro must render <tr class=\"expanded-row\">."""
        pattern = re.compile(
            r'<tr\b[^>]*class="[^"]*expanded-row[^"]*"'
        )
        assert pattern.search(timeline), \
            "expanded_row must render <tr class=\"expanded-row\">"

    def test_expanded_row_data_attr(self, timeline):
        """expanded-row must have data-trace-detail."""
        assert "data-trace-detail" in timeline, \
            "Missing data-trace-detail on expanded-row"

    def test_expanded_row_id_pattern(self, timeline):
        """expanded-row id must match round-{id}-detail pattern."""
        pattern = re.compile(r'id="round-\{\{[^}]+\}\}-detail"')
        assert pattern.search(timeline), \
            "Missing round-{id}-detail id pattern"

    def test_trace_round_calls_both_macros(self, timeline):
        """trace_round macro must call round_row and expanded_row."""
        assert "{{ round_row(row) }}" in timeline, \
            "trace_round must call round_row"
        assert "{{ expanded_row(row) }}" in timeline, \
            "trace_round must call expanded_row"

    def test_session_calls_trace_round(self, session):
        """session.html must call sdt.trace_round for each row."""
        assert "sdt.trace_round(row)" in session, \
            "session.html must call sdt.trace_round(row)"
        assert "for row in trace_rows" in session, \
            "session.html must iterate over trace_rows"

    def test_round_row_has_is_open_class(self, timeline):
        """round-row must support is-open class for expanded state."""
        assert "is-open" in timeline, \
            "Missing is-open class support in round-row"

    def test_row_clickable_for_toggle(self, timeline):
        """Round rows must be clickable to toggle (cursor:pointer on round-row)."""
        assert "data-trace-round-row" in timeline, \
            "Missing data-trace-round-row on round rows"
        assert "is-open" in timeline, \
            "Missing is-open class support for expanded state"


# ── Filter buttons ───────────────────────────────────────────────────


class TestFilterButtons:
    """Trace header must have filter buttons with correct data-actions."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read(TIMELINE_HTML)

    def test_filter_status_action(self, timeline):
        """Filter buttons must use status-all and status-failed actions (no filter-status)."""
        assert 'data-action="filter-status"' not in timeline, \
            "Duplicate data-action='filter-status' must be removed; use status-all/status-failed instead"
        assert 'data-action="status-all"' in timeline or 'data-action="status-failed"' in timeline, \
            "Must have status-all or status-failed action"

    def test_status_all_button(self, timeline):
        """Must have status-all button."""
        assert 'data-action="status-all"' in timeline, \
            "Missing status-all button"

    def test_status_failed_button(self, timeline):
        """Must have status-failed button."""
        assert 'data-action="status-failed"' in timeline, \
            "Missing status-failed button"

    def test_collapse_all_button(self, timeline):
        """Must NOT have separate collapse-all button; toggle-all is the single control."""
        assert 'data-action="collapse-all"' not in timeline, \
            "collapse-all button must be removed; use toggle-all only"
        assert 'data-action="toggle-all"' in timeline, \
            "Missing toggle-all button"

    def test_filter_buttons_in_seg_group(self, timeline):
        """Filter buttons must be in a segmented control group."""
        assert 'class="sd-seg"' in timeline, \
            "Missing sd-seg group for filter buttons"
        assert "sd-seg-btn" in timeline, \
            "Missing sd-seg-btn class for filter buttons"

    def test_status_all_is_active_by_default(self, timeline):
        """status-all button should be active by default."""
        # Find the status-all button and check it has is-active
        all_btn_match = re.search(
            r'<button[^>]*data-action="status-all"[^>]*>',
            timeline
        )
        assert all_btn_match, "Could not find status-all button"
        assert "is-active" in all_btn_match.group(0), \
            "status-all button should have is-active class"

    def test_trace_actions_container(self, timeline):
        """Filter buttons must be in sd-trace-actions container."""
        assert "sd-trace-actions" in timeline, \
            "Missing sd-trace-actions container"


# ── Token bar 4-segment structure ────────────────────────────────────


class TestTokenBar:
    """Token bar must have 4 segments: fresh, read, write, out."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read(TIMELINE_HTML)

    @pytest.fixture(scope="class")
    def primitives(self):
        return _read(PRIMITIVES_HTML)

    def test_tokenbar_in_row(self, timeline):
        """round-row must contain tokenbar element."""
        assert 'class="tokenbar"' in timeline, \
            "Missing .tokenbar in round-row"

    def test_tokenbar_aria_hidden(self, timeline):
        """Tokenbar must be aria-hidden (decorative)."""
        assert 'aria-hidden="true"' in timeline, \
            "Tokenbar should be aria-hidden"

    def test_fresh_segment(self, timeline):
        """Tokenbar must have fresh segment."""
        pattern = re.compile(r'class="fresh"')
        assert pattern.search(timeline), \
            "Missing fresh segment in tokenbar"
        assert "--segment-width" in timeline, \
            "Missing --segment-width CSS variable"

    def test_read_segment(self, timeline):
        """Tokenbar must have read segment."""
        pattern = re.compile(r'class="read"')
        assert pattern.search(timeline), \
            "Missing read segment in tokenbar"

    def test_write_segment(self, timeline):
        """Tokenbar must have write segment."""
        pattern = re.compile(r'class="write"')
        assert pattern.search(timeline), \
            "Missing write segment in tokenbar"

    def test_out_segment(self, timeline):
        """Tokenbar must have out segment."""
        pattern = re.compile(r'class="out"')
        assert pattern.search(timeline), \
            "Missing out segment in tokenbar"

    def test_token_mix_data(self, timeline):
        """Tokenbar segments must be driven by row.token_mix."""
        assert "row.token_mix.fresh" in timeline, \
            "Missing token_mix.fresh data binding"
        assert "row.token_mix.read" in timeline, \
            "Missing token_mix.read data binding"
        assert "row.token_mix.write" in timeline, \
            "Missing token_mix.write data binding"
        assert "row.token_mix.out" in timeline, \
            "Missing token_mix.out data binding"

    def test_primitives_token_bar_macro(self, primitives):
        """Primitives must define token_bar macro (3-segment variant)."""
        assert "{% macro token_bar" in primitives, \
            "Missing token_bar macro in primitives"
        assert "sd-tokenbar" in primitives, \
            "Missing sd-tokenbar class in primitives macro"
        assert "sd-tokenbar__fresh" in primitives, \
            "Missing sd-tokenbar__fresh segment"
        assert "sd-tokenbar__cache" in primitives, \
            "Missing sd-tokenbar__cache segment"
        assert "sd-tokenbar__out" in primitives, \
            "Missing sd-tokenbar__out segment"


# ── Payload modal data attributes ────────────────────────────────────


class TestPayloadModal:
    """Payload modal must have correct structure and data attributes."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read(TIMELINE_HTML)

    @pytest.fixture(scope="class")
    def primitives(self):
        return _read(PRIMITIVES_HTML)

    def test_modal_element_exists(self, timeline):
        """Payload modal must use <dialog> element."""
        assert "<dialog" in timeline, "Missing <dialog> for payload modal"
        assert 'id="payload-modal"' in timeline, \
            "Missing id=\"payload-modal\""
        assert "sd-payload-modal" in timeline, \
            "Missing .sd-payload-modal class"

    def test_modal_title(self, timeline):
        """Modal must have title with data-payload-title."""
        assert "data-payload-title" in timeline, \
            "Missing data-payload-title"
        assert 'id="payload-title"' in timeline, \
            "Missing payload-title id"
        assert 'aria-labelledby="payload-title"' in timeline, \
            "Modal missing aria-labelledby"

    def test_modal_subtitle(self, timeline):
        """Modal must have subtitle area."""
        assert "data-payload-subtitle" in timeline, \
            "Missing data-payload-subtitle"

    def test_modal_close_button(self, timeline):
        """Modal must have close button with close-payload action."""
        assert 'data-action="close-payload"' in timeline, \
            "Missing close-payload action"
        assert "sd-modal-close" in timeline, \
            "Missing sd-modal-close class"

    def test_modal_metadata(self, timeline):
        """Modal body has data-payload-body; metadata lives in payload source templates."""
        # Modal shell: must have body container for content injection
        assert "data-payload-body" in timeline, "Missing data-payload-body"
        # Payload source template: metadata stored as data-* attrs on <template>
        assert "data-payload-kind" in timeline, "Missing data-payload-kind"
        assert "data-payload-status" in timeline, "Missing data-payload-status"
        assert "data-payload-size" in timeline, "Missing data-payload-size"
        # Metadata card inside each template
        assert "sd-payload-meta" in timeline, "Missing sd-payload-meta metadata card"

    def test_modal_body(self, timeline):
        """Modal must have body container with data-payload-body."""
        assert "data-payload-body" in timeline, \
            "Missing data-payload-body"

    def test_modal_empty_state(self, timeline):
        """Modal must have empty state when no payload selected."""
        assert "data-payload-empty" in timeline, \
            "Missing data-payload-empty"
        assert "sd-payload-empty-state" in timeline, \
            "Missing .sd-payload-empty-state"

    def test_payload_source_template(self, timeline):
        """Payload sources must use <template> with data attributes."""
        assert "<template" in timeline, \
            "Missing <template> for payload sources"
        assert "data-payload-source" in timeline, \
            "Missing data-payload-source"
        assert "data-payload-kind" in timeline, \
            "Missing data-payload-kind"
        assert "data-payload-status" in timeline, \
            "Missing data-payload-status"
        assert "data-payload-size" in timeline, \
            "Missing data-payload-size"

    def test_open_payload_buttons(self, timeline, primitives):
        """LLM call card and tool batch must have open-payload buttons."""
        # The sdp.button() macro in primitives renders data-action from the action param
        assert "open-payload" in timeline, \
            "Missing open-payload action in timeline"
        assert 'data-action=' in primitives, \
            "Primitives button macro must support data-action"
        assert 'data-payload-id=' in primitives, \
            "Primitives button macro must support data-payload-id"

    def test_context_payload_button(self, timeline):
        """LLM call card must have Context button."""
        assert "Context" in timeline, "Missing Context button"
        assert 'data-payload-kind="context"' in timeline, \
            "Missing data-payload-kind=\"context\""

    def test_response_payload_button(self, timeline):
        """LLM call card must have Response button."""
        assert "Response" in timeline, "Missing Response button"
        assert 'data-payload-kind="response"' in timeline, \
            "Missing data-payload-kind=\"response\""

    def test_result_payload_button(self, timeline):
        """Tool batch must have Result button."""
        assert "Result" in timeline, "Missing Result button"
        # Result button uses data-payload-kind="result"
        assert 'data-payload-kind="result"' in timeline, \
            'Missing data-payload-kind="result"'


# ── Session page-level markers ───────────────────────────────────────


class TestSessionPageMarkers:
    """Session page must have page-level markers for JS wiring."""

    @pytest.fixture(scope="class")
    def session(self):
        return _read(SESSION_HTML)

    def test_trace_page_marker(self, session):
        """Session content must have data-trace-page."""
        assert "data-trace-page" in session, \
            "Missing data-trace-page marker"

    def test_sd_shell_wrapper(self, session):
        """Session content must have sd-shell class."""
        assert "sd-shell" in session, \
            "Missing sd-shell class"

    def test_session_id_meta(self, session):
        """Session must expose session-id via <meta>."""
        assert 'name="session-id"' in session, \
            "Missing <meta name=\"session-id\">"

    def test_payload_api_base_meta(self, session):
        """Session must expose payload API base via <meta>."""
        assert 'name="payload-api-base"' in session, \
            "Missing <meta name=\"payload-api-base\">"

    def test_session_detail_css(self, session):
        """Session must include session-detail.css."""
        assert "session-detail.css" in session, \
            "Missing session-detail.css link"

    def test_session_detail_js(self, session):
        """Session must include session-detail.js."""
        assert "session-detail.js" in session, \
            "Missing session-detail.js script"

    def test_trace_panel_container(self, session):
        """Session must have data-trace-panel container."""
        assert "data-trace-panel" in session, \
            "Missing data-trace-panel"
        assert "sd-trace-panel" in session, \
            "Missing .sd-trace-panel"

    def test_payload_sources_macro_call(self, session):
        """Session must call payload_sources macro."""
        assert "sdt.payload_sources" in session, \
            "Missing sdt.payload_sources macro call"

    def test_payload_modal_macro_call(self, session):
        """Session must call payload_modal macro."""
        assert "sdt.payload_modal" in session, \
            "Missing sdt.payload_modal macro call"

    def test_no_content_modal(self, session):
        """content-modal must NOT exist (removed in v9+)."""
        assert 'id="content-modal"' not in session, \
            "content-modal must be removed"

    def test_no_workbench_views(self, session):
        """Old workbench views must NOT exist."""
        assert 'data-workbench-view="calls"' not in session, \
            "calls workbench view must be removed"
        assert 'data-workbench-view="hotspots"' not in session, \
            "hotspots workbench view must be removed"
