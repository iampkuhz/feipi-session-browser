"""TASK-035: Session Detail QA 与回归测试 (Phase 1 simplified)

Covers:
- Trace-first debug page (single view, no tab switching)
- Issue Summary section with failed rounds and high-token rounds
- Trace panel with All/Failed filter, Expand/Collapse
- Payload modal with Rendered/Raw tabs
- Content modal compatibility
- Metrics strip and anomaly banner
- Inspector integration (tool spans, openToolInspector)
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# Shell and core structure
# ──────────────────────────────────────────────────────────────────────


class TestShellStructure:

    def _source(self):
        return _session_source()

    def test_session_detail_shell_exists(self):
        source = self._source()
        assert 'data-session-detail-shell' in source, \
            "Session detail shell must exist"

    def test_session_id_set_for_js(self):
        source = self._source()
        assert "window._sessionId" in source, \
            "Session ID must be set for JS state persistence"

    def test_hero_section_exists(self):
        source = self._source()
        assert 'data-session-overview-hero' in source, \
            "Hero section must exist"

    def test_no_old_workbench_views(self):
        """Calls and Hotspots workbench views should be removed."""
        source = self._source()
        assert 'data-workbench-view="calls"' not in source, \
            "calls view should be removed"
        assert 'data-workbench-view="hotspots"' not in source, \
            "hotspots view should be removed"
        assert 'data-workbench' not in source, \
            "workbench container should be removed"


# ──────────────────────────────────────────────────────────────────────
# Issue Summary
# ──────────────────────────────────────────────────────────────────────


class TestIssueSummary:

    def _source(self):
        return _session_source()

    def test_issue_summary_section_exists(self):
        source = self._source()
        assert 'data-issue-summary' in source, \
            "Issue summary section must exist"

    def test_has_issue_cards(self):
        source = self._source()
        assert 'class="issue-card"' in source or 'issue-card--' in source, \
            "Issue summary must have issue-card elements"

    def test_has_empty_state(self):
        source = self._source()
        assert "No actionable issues detected" in source, \
            "Issue summary must have empty state"

    def test_issue_cards_have_jump_action(self):
        source = self._source()
        assert 'data-action="jump-round"' in source, \
            "Issue cards must have jump-round action"
        assert 'data-round=' in source, \
            "Issue cards must have data-round attribute"


# ──────────────────────────────────────────────────────────────────────
# Trace Panel
# ──────────────────────────────────────────────────────────────────────


class TestTracePanel:

    def _source(self):
        return _session_source()

    def test_trace_panel_exists(self):
        source = self._source()
        assert 'data-trace-panel' in source or 'class="trace-panel"' in source, \
            "Trace panel must exist"

    def test_trace_toolbar_exists(self):
        source = self._source()
        assert 'class="trace-panel__toolbar"' in source, \
            "Trace panel must have toolbar"

    def test_has_all_failed_segmented_control(self):
        source = self._source()
        assert 'data-action="filter-status"' in source, \
            "Trace must have filter-status action"
        assert 'data-status="all"' in source, \
            "Trace must have 'all' filter chip"
        assert 'data-status="failed"' in source, \
            "Trace must have 'failed' filter chip"

    def test_has_expand_all_button(self):
        source = self._source()
        # Renamed to 'expand-visible' — only expands non-filtered rows
        assert 'data-action="expand-visible"' in source, \
            "Trace must have Expand Visible button"

    def test_has_collapse_all_button(self):
        source = self._source()
        assert 'data-action="collapse-all"' in source, \
            "Trace must have Collapse All button"

    def test_has_trace_row_structure(self):
        source = self._source()
        assert 'class="trace-row"' in source, \
            "Trace must have trace-row elements"
        assert 'data-round-idx=' in source, \
            "Trace rows must have data-round-idx"

    def test_has_trace_detail(self):
        source = self._source()
        assert 'class="trace-detail"' in source, \
            "Trace must have trace-detail elements"
        assert 'data-round-detail=' in source, \
            "Trace detail must have data-round-detail attribute"

    def test_trace_row_has_status(self):
        source = self._source()
        assert 'data-status=' in source, \
            "Trace rows must have data-status attribute"

    def test_span_list_structure(self):
        source = self._source()
        assert 'span-list' in source, \
            "Trace detail must have span-list"
        # After Task 03, LLM spans are rendered as .llm-call-card instead of .span.llm
        assert 'class="llm-call-card"' in source, \
            "LLM calls must be rendered as .llm-call-card"

    def test_tool_spans_have_data_attrs(self):
        source = self._source()
        for attr in ["data-tool-name=", "data-tool-status=", "data-tool-idx=",
                      "data-tool-scope="]:
            assert attr in source, f"Tool spans must have {attr}"

    def test_tool_spans_have_exit_code(self):
        source = self._source()
        assert "data-tool-exit-code=" in source, \
            "Tool spans must have data-tool-exit-code"

    def test_tool_spans_have_duration(self):
        source = self._source()
        assert "data-tool-duration-ms=" in source, \
            "Tool spans must have data-tool-duration-ms"

    def test_tool_spans_have_error(self):
        source = self._source()
        assert "data-tool-error=" in source, \
            "Tool spans must have data-tool-error"

    def test_has_build_timeline_nodes_macro(self):
        source = self._source()
        assert "build_timeline_nodes" in source, \
            "Must define build_timeline_nodes macro"

    def test_imports_timeline_component(self):
        source = self._source()
        assert 'from "components/timeline.html" import' in source, \
            "Must import timeline component macros"

    def test_imports_viewer_component(self):
        source = self._source()
        assert 'from "components/viewer.html" import viewer' in source, \
            "Must import viewer component"

    def test_toggleRoundDetail_js(self):
        source = self._source()
        assert "toggleRoundDetail" in source, \
            "Must have toggleRoundDetail JS function"

    def test_has_render_tool_result_macro(self):
        source = self._source()
        assert "render_tool_result" in source, \
            "Must have render_tool_result macro"


# ──────────────────────────────────────────────────────────────────────
# Payload Modal
# ──────────────────────────────────────────────────────────────────────


class TestPayloadModal:

    def _source(self):
        return _base_source()

    def test_payload_modal_element_exists(self):
        source = self._source()
        assert 'id="payload-modal"' in source, \
            "payload-modal element must exist"

    def test_payload_modal_has_header(self):
        source = self._source()
        assert 'class="payload-modal__header"' in source, \
            "Modal must have header"

    def test_payload_modal_has_title(self):
        source = self._source()
        assert 'class="payload-modal__title"' in source, \
            "Modal must have title element"

    def test_payload_modal_has_rendered_tab(self):
        source = self._source()
        assert 'data-mode="rendered"' in source, \
            "Modal must have Rendered tab"

    def test_payload_modal_has_raw_tab(self):
        source = self._source()
        assert 'data-mode="raw"' in source, \
            "Modal must have Raw tab"

    def test_payload_modal_has_close_button(self):
        source = self._source()
        assert 'data-action="close-modal"' in source, \
            "Modal must have close button"

    def test_payload_modal_has_rendered_section(self):
        source = self._source()
        assert 'class="payload-modal__rendered"' in source, \
            "Modal must have rendered section"

    def test_payload_modal_has_raw_section(self):
        source = self._source()
        assert 'class="payload-modal__raw"' in source, \
            "Modal must have raw section"

    def test_payload_registry_exists(self):
        source = _session_source()
        assert "window.__SESSION_PAYLOADS__" in source, \
            "Must have payload registry script in session.html"

    def test_escape_key_closes_modal(self):
        source = _session_source()
        assert "Escape" in source, \
            "Must handle Escape key for payload modal in session.html"


# ──────────────────────────────────────────────────────────────────────
# Content modal removed in Phase 1.1 — negative assertions
# ──────────────────────────────────────────────────────────────────────


class TestContentViewerModalRemoved:

    def _source(self):
        return _session_source()

    def test_content_modal_element_removed(self):
        source = self._source()
        assert 'id="content-modal"' not in source, \
            "content-modal element must be removed (Phase 1.1)"

    def test_content_modal_js_removed(self):
        source = self._source()
        assert "openContentModal" not in source, \
            "openContentModal JS must be removed (Phase 1.1)"
        assert "closeContentModal" not in source, \
            "closeContentModal JS must be removed (Phase 1.1)"
        assert "switchContentView" not in source, \
            "switchContentView JS must be removed (Phase 1.1)"


# ──────────────────────────────────────────────────────────────────────
# Tool Inspector integration
# ──────────────────────────────────────────────────────────────────────


class TestToolInspector:

    def _source(self):
        return _session_source()

    def _base(self):
        return _base_source()

    def test_openInspector_available(self):
        source = self._source()
        assert "window.openInspector" in source, \
            "openToolInspector must check for window.openInspector"

    def test_openInspector_called(self):
        source = self._source()
        assert "openInspector({" in source, \
            "Must call openInspector with config object"

    def test_html_escaping(self):
        source = self._source()
        # Must escape HTML to prevent XSS in raw viewer
        assert "replace" in source and "&amp;" in source, \
            "Must escape HTML entities in raw content"

    def test_base_template_has_inspector(self):
        base = self._base()
        assert "inspector" in base.lower(), \
            "base.html must contain inspector references"


# ──────────────────────────────────────────────────────────────────────
# Metrics Strip
# ──────────────────────────────────────────────────────────────────────


class TestMetricsStrip:

    def _source(self):
        return _session_source()

    def test_metrics_strip_card_exists(self):
        source = self._source()
        assert 'class="kpis"' in source or \
               'class="hero-secondary-metrics"' in source or \
               'class="metrics-strip-card"' in source, \
            "Metrics must exist as .kpis or .hero-secondary-metrics"

    def test_has_duration_metric(self):
        source = self._source()
        assert '时长' in source or 'Duration' in source, \
            "Metrics must include duration metric"

    def test_has_rounds_metric(self):
        source = self._source()
        assert '轮次' in source or 'Rounds' in source, \
            "Metrics must include rounds metric"

    def test_has_total_token_metric(self):
        source = self._source()
        assert '总 Token' in source or 'Total Token' in source, \
            "Metrics must include total token metric"

    def test_has_tool_call_metric(self):
        source = self._source()
        assert '工具调用' in source or 'Tool Call' in source, \
            "Metrics must include tool call metric"


# ──────────────────────────────────────────────────────────────────────
# Anomaly Banner
# ──────────────────────────────────────────────────────────────────────


class TestAnomalyBanner:

    def _source(self):
        return _session_source()

    def test_anomaly_banner_template_exists(self):
        source = self._source()
        assert 'anomaly-inline anomaly-banner' in source, \
            "Anomaly banner template must exist"

    def test_anomaly_banner_has_severity_badges(self):
        source = self._source()
        assert "anomaly-banner__severity-label" in source, \
            "Anomaly banner must show severity label"

    def test_anomaly_banner_has_anomaly_badges(self):
        source = self._source()
        assert "anomaly-badge" in source, \
            "Anomaly banner must render anomaly-badge elements"

    def test_has_anomalies_conditional(self):
        source = self._source()
        assert "has_anomalies" in source, \
            "Anomaly banner must be conditionally rendered via has_anomalies"

    def test_no_calls_or_hotspots_targets(self):
        """Hero alerts should not reference calls or hotspots target views."""
        source = self._source()
        # The old target_view='calls' and target_view='hotspots' should be gone
        assert "target_view': 'calls'" not in source, \
            "Hero alerts should not target calls view"
        assert "target_view': 'hotspots'" not in source, \
            "Hero alerts should not target hotspots view"

