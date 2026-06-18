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

import pytest
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"
SESSION_HTML = TEMPLATE_DIR / "session.html"
TIMELINE_HTML = COMPONENTS / "session_detail_timeline.html"
TIMELINE_DIR = COMPONENTS / "session_detail_timeline"
PRIMITIVES_HTML = COMPONENTS / "session_detail_primitives.html"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        pytest.fail(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def _read_timeline_with_splits() -> str:
    """Read main timeline file and all split subdirectory files."""
    parts = []
    if TIMELINE_HTML.exists():
        parts.append(TIMELINE_HTML.read_text(encoding="utf-8"))
    if TIMELINE_DIR.is_dir():
        for f in sorted(TIMELINE_DIR.glob("*.html")):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


# ── 主视觉区 ────────────────────────────────────────────────────────


class TestHeroArea:
    """Hero area must have agent pill, KPIs, and summary strip."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read_timeline_with_splits()

    @pytest.mark.contract_case("UI-SD-001")
    def test_hero_section_exists(self, timeline):
        """Hero section must use .sd-hero with data-session-overview-hero."""
        assert 'class="sd-hero"' in timeline, "Missing .sd-hero class"
        assert "data-session-overview-hero" in timeline, \
            "Hero missing data-session-overview-hero"

    @pytest.mark.contract_case("UI-SD-001")
    def test_agent_pill_exists(self, timeline):
        """Hero must render agent pill."""
        assert "sd-agent-pill" in timeline, "Missing sd-agent-pill in hero"
        assert "summary.agent_label" in timeline, \
            "Hero must render summary.agent_label"

    @pytest.mark.contract_case("UI-SD-001")
    def test_hero_title_exists(self, timeline):
        """Hero must have h1 title with summary.title."""
        assert "<h1" in timeline, "Missing h1 title in hero"
        assert "summary.title" in timeline, \
            "Hero title must use summary.title"

    @pytest.mark.contract_case("UI-SD-001")
    def test_hero_meta_chips(self, timeline):
        """Hero must show model, project, date chips (short-id moved to breadcrumb)."""
        assert "summary.model" in timeline, "Missing model chip in hero"
        assert "summary.project_name" in timeline, \
            "Missing project chip in hero"
        assert "summary.date" in timeline, "Missing date chip in hero"

    @pytest.mark.contract_case("UI-SD-034")
    def test_hero_session_file_path_copy(self, timeline):
        """Hero must show the local session file path with a copy action."""
        assert "data-session-file-path" in timeline, "Missing session file path hook"
        assert "summary.session_file_path" in timeline, \
            "Hero must render summary.session_file_path"
        assert "Copy session file path" in timeline, \
            "Hero must provide a session file path copy button"
        assert 'data-action="copy"' in timeline, \
            "Session file path copy must use the canonical copy action"

    @pytest.mark.contract_case("UI-SD-001")
    def test_kpi_container_exists(self, timeline):
        """KPI container must use .sd-kpis."""
        assert 'class="sd-kpis"' in timeline, "Missing .sd-kpis container"

    @pytest.mark.contract_case("UI-SD-001")
    def test_kpi_tokens(self, timeline):
        """KPIs must include Tokens."""
        assert "sd-kpi" in timeline, "Missing .sd-kpi items"
        # 查找 token KPI 区块
        assert "Tokens" in timeline, "Missing Tokens KPI label"
        assert "metrics.tokens" in timeline, \
            "KPI must render metrics.tokens value"

    @pytest.mark.contract_case("UI-SD-001")
    def test_kpi_run_health(self, timeline):
        """KPIs must include Run Health."""
        assert "Run Health" in timeline, "Missing Run Health KPI label"
        assert "metrics.run_health" in timeline, \
            "KPI must render metrics.run_health value"

    @pytest.mark.contract_case("UI-SD-001")
    def test_kpi_tools(self, timeline):
        """KPIs must include Tools."""
        assert "Tools" in timeline, "Missing Tools KPI label"
        assert "metrics.tool_calls" in timeline, \
            "KPI must render global metrics.tool_calls value"

    @pytest.mark.contract_case("UI-SD-001")
    def test_kpi_failed(self, timeline):
        """KPIs must include Failed."""
        assert "Failed" in timeline, "Missing Failed KPI label"
        assert "metrics.failed_tools" in timeline, \
            "KPI must render metrics.failed_tools value"

    @pytest.mark.contract_case("UI-SD-001")
    def test_summary_strip_exists(self, timeline):
        """Summary strip must exist with data-summary-strip."""
        assert "data-summary-strip" in timeline, \
            "Missing data-summary-strip"
        assert "sd-summary-strip" in timeline, \
            "Missing .sd-summary-strip"

    @pytest.mark.contract_case("UI-SD-001")
    def test_summary_strip_items(self, timeline):
        """Summary strip must keep only short status metadata."""
        assert "sd-summary-item" in timeline, "Missing .sd-summary-item"
        assert "summary.session_id" in timeline, "Missing session id in summary strip"
        assert "summary.model" in timeline, "Missing model in summary strip"
        assert "summary.project_name" in timeline, "Missing project in summary strip"
        assert "summary.date" in timeline, "Missing created date in summary strip"
        assert "metrics.updated" in timeline, "Missing updated timestamp in summary strip"

    @pytest.mark.contract_case("UI-SD-001")
    def test_issue_strip_in_hero(self, timeline):
        """Issue strip must be within hero section."""
        assert "data-issue-strip" in timeline, \
            "Missing data-issue-strip in hero"
        assert "sd-issue-strip" in timeline, \
            "Missing .sd-issue-strip"

    @pytest.mark.contract_case("UI-SD-001")
    def test_issue_strip_has_jump_action(self, timeline):
        """Issue links must use jump-round action."""
        assert 'data-action="jump-round"' in timeline, \
            "Issue links missing data-action=\"jump-round\""
        assert "data-round=" in timeline, \
            "Issue links missing data-round attribute"


# ── Tab navigation ───────────────────────────────────────────────────


class TestTabNavigation:
    """Tab navigation must have Trace and Payload tabs."""

    @pytest.fixture(scope="class")
    def session(self):
        return _read(SESSION_HTML)

    @pytest.mark.contract_case("UI-SD-001")
    def test_tab_container_exists(self, session):
        """Tab nav must use .sd-tabs with data-session-tabs."""
        assert 'class="sd-tabs"' in session, "Missing .sd-tabs container"
        assert "data-session-tabs" in session, \
            "Missing data-session-tabs attribute"

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_tab_exists(self, session):
        """Trace tab must exist with data-action=\"tab-trace\"."""
        assert 'data-action="tab-trace"' in session, \
            "Missing Trace tab"
        assert 'data-tab="trace"' in session, \
            "Missing data-tab=\"trace\""

    @pytest.mark.contract_case("UI-SD-001")
    def test_payload_tab_exists(self, session):
        """Payload tab must exist with data-action=\"tab-payload\"."""
        assert 'data-action="tab-payload"' in session, \
            "Missing Payload tab"
        assert 'data-tab="payload"' in session, \
            "Missing data-tab=\"payload\""

    @pytest.mark.contract_case("UI-SD-001")
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

    @pytest.mark.contract_case("UI-SD-001")
    def test_tab_aria_label(self, session):
        """Tab nav must have accessible aria-label."""
        assert 'aria-label="Session view tabs"' in session, \
            "Tab nav missing aria-label"


# ── Trace table structure ────────────────────────────────────────────


class TestTraceTableStructure:
    """Trace table must use round-row + expanded-row <tr> pattern."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read_timeline_with_splits()

    @pytest.fixture(scope="class")
    def session(self):
        return _read(SESSION_HTML)

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_table_element(self, session):
        """session.html must have <table class=\"trace-table\">."""
        assert 'class="trace-table"' in session, \
            "Missing <table class=\"trace-table\">"

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_table_data_attr(self, session):
        """Trace table must have data-trace-list."""
        assert "data-trace-list" in session, \
            "Missing data-trace-list on table"

    @pytest.mark.contract_case("UI-SD-001")
    def test_colgroup_structure(self, session):
        """Table must have colgroup with expected columns."""
        assert "<colgroup>" in session, "Missing <colgroup>"
        assert "col-round" in session, "Missing col-round"
        assert "col-summary" in session, "Missing col-summary"
        assert "col-metrics" in session, "Missing col-metrics"
        assert "col-status" in session, "Missing col-status"

    @pytest.mark.contract_case("UI-SD-001")
    def test_thead_structure(self, session):
        """Table must have <thead> with column headers."""
        assert "<thead>" in session, "Missing <thead>"
        assert "round-col" in session, "Missing round column header"
        assert "metrics-col" in session, "Missing metrics column header"
        assert "status-col" in session, "Missing status column header"

    @pytest.mark.contract_case("UI-SD-001")
    def test_round_row_is_tr(self, timeline):
        """round_row macro must render <tr class=\"round-row\">."""
        pattern = re.compile(
            r'<tr\b[^>]*class="[^"]*round-row[^"]*"'
        )
        assert pattern.search(timeline), \
            "round_row must render <tr class=\"round-row\">"

    @pytest.mark.contract_case("UI-SD-001")
    def test_round_row_data_attrs(self, timeline):
        """round-row must have data-trace-round-row, data-round, data-status."""
        assert "data-trace-round-row" in timeline, \
            "Missing data-trace-round-row"
        pattern = re.compile(r'data-round="\{\{\s*row\.round_id\s*\}\}"')
        assert pattern.search(timeline), \
            "Missing data-round template attribute"
        assert 'data-status="' in timeline, \
            "Missing data-status on round-row"

    @pytest.mark.contract_case("UI-SD-001")
    def test_expanded_row_is_tr(self, timeline):
        """expanded_row macro must render <tr class=\"expanded-row\">."""
        pattern = re.compile(
            r'<tr\b[^>]*class="[^"]*expanded-row[^"]*"'
        )
        assert pattern.search(timeline), \
            "expanded_row must render <tr class=\"expanded-row\">"

    @pytest.mark.contract_case("UI-SD-001")
    def test_expanded_row_data_attr(self, timeline):
        """expanded-row must have data-trace-detail."""
        assert "data-trace-detail" in timeline, \
            "Missing data-trace-detail on expanded-row"

    @pytest.mark.contract_case("UI-SD-001")
    def test_expanded_row_id_pattern(self, timeline):
        """expanded-row id must match round-{id}-detail pattern."""
        pattern = re.compile(r'id="round-\{\{[^}]+\}\}-detail"')
        assert pattern.search(timeline), \
            "Missing round-{id}-detail id pattern"

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_round_calls_both_macros(self, timeline):
        """trace_round macro must call round_row and expanded_row."""
        assert "{{ round_row(row) }}" in timeline, \
            "trace_round must call round_row"
        assert "{{ expanded_row(row) }}" in timeline, \
            "trace_round must call expanded_row"

    @pytest.mark.contract_case("UI-SD-001")
    def test_session_calls_trace_round(self, session):
        """session.html must call sdt.trace_round for each row."""
        assert "sdt.trace_round(row" in session, \
            "session.html must call sdt.trace_round(row, ...)"
        assert "for row in trace_rows" in session, \
            "session.html must iterate over trace_rows"

    @pytest.mark.contract_case("UI-SD-001")
    def test_round_row_has_is_open_class(self, timeline):
        """round-row must support is-open class for expanded state."""
        assert "is-open" in timeline, \
            "Missing is-open class support in round-row"

    @pytest.mark.contract_case("UI-SD-001")
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
        return _read_timeline_with_splits()

    @pytest.mark.contract_case("UI-SD-001")
    def test_filter_status_action(self, timeline):
        """Filter buttons must use status-all and status-failed actions (no filter-status)."""
        assert 'data-action="filter-status"' not in timeline, \
            "Duplicate data-action='filter-status' must be removed; use status-all/status-failed instead"
        assert 'data-action="status-all"' in timeline or 'data-action="status-failed"' in timeline, \
            "Must have status-all or status-failed action"

    @pytest.mark.contract_case("UI-SD-001")
    def test_status_all_button(self, timeline):
        """Must have status-all button."""
        assert 'data-action="status-all"' in timeline, \
            "Missing status-all button"

    @pytest.mark.contract_case("UI-SD-001")
    def test_status_failed_button(self, timeline):
        """Must have status-failed button."""
        assert 'data-action="status-failed"' in timeline, \
            "Missing status-failed button"

    @pytest.mark.contract_case("UI-SD-001")
    def test_status_low_cache_button(self, timeline):
        """Must have status-low-cache button."""
        assert 'data-action="status-low-cache"' in timeline, \
            "Missing status-low-cache button"

    @pytest.mark.contract_case("UI-SD-001")
    def test_collapse_all_button(self, timeline):
        """Must NOT have separate collapse-all button; toggle-all is the single control."""
        assert 'data-action="collapse-all"' not in timeline, \
            "collapse-all button must be removed; use toggle-all only"
        assert 'data-action="toggle-all"' in timeline, \
            "Missing toggle-all button"

    @pytest.mark.contract_case("UI-SD-001")
    def test_filter_buttons_in_seg_group(self, timeline):
        """Filter buttons must be in a segmented control group."""
        assert 'class="sd-seg"' in timeline, \
            "Missing sd-seg group for filter buttons"
        assert "sd-seg-btn" in timeline, \
            "Missing sd-seg-btn class for filter buttons"

    @pytest.mark.contract_case("UI-SD-001")
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

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_actions_container(self, timeline):
        """Filter buttons must be in sd-trace-actions container."""
        assert "sd-trace-actions" in timeline, \
            "Missing sd-trace-actions container"


# ── Token bar 4-segment structure ────────────────────────────────────


class TestTokenBar:
    """Token bar must have 4 segments: fresh, read, write, out."""

    @pytest.fixture(scope="class")
    def timeline(self):
        return _read_timeline_with_splits()

    @pytest.fixture(scope="class")
    def primitives(self):
        return _read(PRIMITIVES_HTML)

    @pytest.mark.contract_case("UI-SD-001")
    def test_tokenbar_in_row(self, timeline):
        """round-row must contain tokenbar element."""
        assert 'class="tokenbar"' in timeline, \
            "Missing .tokenbar in round-row"

    @pytest.mark.contract_case("UI-SD-001")
    def test_tokenbar_aria_hidden(self, timeline):
        """Tokenbar must be aria-hidden (decorative)."""
        assert 'aria-hidden="true"' in timeline, \
            "Tokenbar should be aria-hidden"

    @pytest.mark.contract_case("UI-SD-001")
    def test_fresh_segment(self, timeline):
        """Tokenbar must have fresh segment."""
        pattern = re.compile(r'class="fresh"')
        assert pattern.search(timeline), \
            "Missing fresh segment in tokenbar"
        assert "--segment-width" in timeline, \
            "Missing --segment-width CSS variable"

    @pytest.mark.contract_case("UI-SD-001")
    def test_read_segment(self, timeline):
        """Tokenbar must have read segment."""
        pattern = re.compile(r'class="read"')
        assert pattern.search(timeline), \
            "Missing read segment in tokenbar"

    @pytest.mark.contract_case("UI-SD-001")
    def test_write_segment(self, timeline):
        """Tokenbar must have write segment."""
        pattern = re.compile(r'class="write"')
        assert pattern.search(timeline), \
            "Missing write segment in tokenbar"

    @pytest.mark.contract_case("UI-SD-001")
    def test_out_segment(self, timeline):
        """Tokenbar must have out segment."""
        pattern = re.compile(r'class="out"')
        assert pattern.search(timeline), \
            "Missing out segment in tokenbar"

    @pytest.mark.contract_case("UI-SD-001")
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

    @pytest.mark.contract_case("UI-SD-001")
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
        return _read_timeline_with_splits()

    @pytest.fixture(scope="class")
    def primitives(self):
        return _read(PRIMITIVES_HTML)

    @pytest.mark.contract_case("UI-SD-001")
    def test_modal_element_exists(self, timeline):
        """Payload modal must use <dialog> element."""
        assert "<dialog" in timeline, "Missing <dialog> for payload modal"
        assert 'id="payload-modal"' in timeline, \
            "Missing id=\"payload-modal\""
        assert "sd-payload-modal" in timeline, \
            "Missing .sd-payload-modal class"

    @pytest.mark.contract_case("UI-SD-001")
    def test_modal_title(self, timeline):
        """Modal must have title with data-payload-title."""
        assert "data-payload-title" in timeline, \
            "Missing data-payload-title"
        assert 'id="payload-title"' in timeline, \
            "Missing payload-title id"
        assert 'aria-labelledby="payload-title"' in timeline, \
            "Modal missing aria-labelledby"

    @pytest.mark.contract_case("UI-SD-001")
    def test_modal_subtitle(self, timeline):
        """Modal must have subtitle area."""
        assert "data-payload-subtitle" in timeline, \
            "Missing data-payload-subtitle"

    @pytest.mark.contract_case("UI-SD-001")
    def test_modal_close_button(self, timeline):
        """Modal must have close button with close-payload action."""
        assert 'data-action="close-payload"' in timeline, \
            "Missing close-payload action"
        assert "sd-modal-close" in timeline, \
            "Missing sd-modal-close class"

    @pytest.mark.contract_case("UI-SD-001")
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

    @pytest.mark.contract_case("UI-SD-001")
    def test_modal_body(self, timeline):
        """Modal must have body container with data-payload-body."""
        assert "data-payload-body" in timeline, \
            "Missing data-payload-body"

    @pytest.mark.contract_case("UI-SD-001")
    def test_modal_empty_state(self, timeline):
        """Modal must have empty state when no payload selected."""
        assert "data-payload-empty" in timeline, \
            "Missing data-payload-empty"
        assert "sd-payload-empty-state" in timeline, \
            "Missing .sd-payload-empty-state"

    @pytest.mark.contract_case("UI-SD-001")
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

    @pytest.mark.contract_case("UI-SD-001")
    def test_open_payload_buttons(self, timeline, primitives):
        """Message, assistant, and tool rows must have open-payload buttons."""
        # The sdp.button() macro in primitives renders data-action from the action param
        assert "open-payload" in timeline, \
            "Missing open-payload action in timeline"
        assert 'data-action=' in primitives, \
            "Primitives button macro must support data-action"
        assert 'data-payload-id=' in primitives, \
            "Primitives button macro must support data-payload-id"

    @pytest.mark.contract_case("UI-SD-001")
    def test_user_message_payload_button(self, timeline):
        """User message row must expose payload access."""
        assert "user_message_event" in timeline, "Missing user message event macro"
        assert 'data-payload-kind="message.user"' in timeline, \
            "Missing data-payload-kind=\"message.user\""

    @pytest.mark.contract_case("UI-SD-001")
    def test_assistant_payload_button(self, timeline):
        """Assistant event rows must expose response payload access."""
        assert "assistant_event" in timeline, "Missing assistant event macro"
        assert 'data-payload-kind="response"' in timeline, \
            "Missing data-payload-kind=\"response\""

    @pytest.mark.contract_case("UI-SD-001")
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

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_page_marker(self, session):
        """Session content must have data-trace-page."""
        assert "data-trace-page" in session, \
            "Missing data-trace-page marker"

    @pytest.mark.contract_case("UI-SD-001")
    def test_sd_shell_wrapper(self, session):
        """Session content must have sd-shell class."""
        assert "sd-shell" in session, \
            "Missing sd-shell class"

    @pytest.mark.contract_case("UI-SD-001")
    def test_session_id_meta(self, session):
        """Session must expose session-id via <meta>."""
        assert 'name="session-id"' in session, \
            "Missing <meta name=\"session-id\">"

    @pytest.mark.contract_case("UI-SD-001")
    def test_payload_api_base_meta(self, session):
        """Session must expose payload API base via <meta>."""
        assert 'name="payload-api-base"' in session, \
            "Missing <meta name=\"payload-api-base\">"

    @pytest.mark.contract_case("UI-SD-001")
    def test_session_detail_css(self, session):
        """Session must include session-detail.css."""
        assert "session-detail.css" in session, \
            "Missing session-detail.css link"

    @pytest.mark.contract_case("UI-SD-001")
    def test_session_detail_js_modules(self, session):
        """Session must include session-detail split modules."""
        assert "/static/js/session-detail/init.js" in session, \
            "Missing session-detail init module"
        assert "/static/js/session-detail/events.js" in session, \
            "Missing session-detail events module"

    @pytest.mark.contract_case("UI-SD-001")
    def test_trace_panel_container(self, session):
        """Session must have data-trace-panel container."""
        assert "data-trace-panel" in session, \
            "Missing data-trace-panel"
        assert "sd-trace-panel" in session, \
            "Missing .sd-trace-panel"

    @pytest.mark.contract_case("UI-SD-001")
    def test_payload_sources_macro_call(self, session):
        """Session must call payload_sources macro."""
        assert "sdt.payload_sources" in session, \
            "Missing sdt.payload_sources macro call"

    @pytest.mark.contract_case("UI-SD-001")
    def test_payload_modal_macro_call(self, session):
        """Session must call payload_modal macro."""
        assert "sdt.payload_modal" in session, \
            "Missing sdt.payload_modal macro call"

    @pytest.mark.contract_case("UI-SD-001")
    def test_no_content_modal(self, session):
        """content-modal must NOT exist (已移除)."""
        assert 'id="content-modal"' not in session, \
            "content-modal must be removed"

    @pytest.mark.contract_case("UI-SD-001")
    def test_no_workbench_views(self, session):
        """Old workbench views must NOT exist."""
        assert 'data-workbench-view="calls"' not in session, \
            "calls workbench view must be removed"
        assert 'data-workbench-view="hotspots"' not in session, \
            "hotspots workbench view must be removed"
