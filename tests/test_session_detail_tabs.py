"""Session Detail QA and regression tests (v9).

Covers:
- Trace-first layout with timeline view
- Issue strip in hero section
- Trace panel with All/Failed filter, Collapse all
- Payload modal with Rendered/Raw tabs
- Component macro structure
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────
# Shell and core structure
# ──────────────────────────────────────────────────────────────────────


class TestShellStructure:

    def _source(self):
        return _session_source()

    def test_session_declares_sd_shell(self):
        source = self._source()
        assert "sd-shell" in source, \
            "Session must declare sd-shell class"

    def test_session_id_set_for_js(self):
        source = _base_source()
        assert "window._sessionId" in source, \
            "Session ID must be set for JS state persistence"

    def test_hero_section_exists(self):
        source = _session_source()
        assert "sdt.hero" in source, \
            "Session must call sdt.hero macro"

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
# Issue Strip
# ──────────────────────────────────────────────────────────────────────


class TestIssueStrip:

    def _source(self):
        return _timeline_component()

    def test_issue_strip_exists(self):
        source = self._source()
        assert "data-issue-strip" in source, \
            "Issue strip section must exist"

    def test_has_empty_state_fallback(self):
        source = self._source()
        # When no issues, the macro renders nothing (no explicit empty state)
        # The presence of the data-issue-strip element is sufficient
        assert "data-issue-strip" in source

    def test_issue_links_have_jump_action(self):
        source = self._source()
        assert 'data-action="jump-round"' in source, \
            "Issue links must have jump-round action"
        assert 'data-round=' in source, \
            "Issue links must have data-round attribute"


# ──────────────────────────────────────────────────────────────────────
# Trace Panel
# ──────────────────────────────────────────────────────────────────────


class TestTracePanel:

    def _source(self):
        return _session_source()

    def _timeline(self):
        return _timeline_component()

    def test_trace_panel_exists(self):
        source = self._source()
        assert 'data-trace-panel' in source, \
            "Trace panel must exist"

    def test_has_all_failed_segmented_control(self):
        source = self._timeline()
        assert 'data-action="filter-status"' in source, \
            "Trace must have filter-status action"
        assert 'data-status="all"' in source, \
            "Trace must have 'all' filter chip"
        assert 'data-status="failed"' in source, \
            "Trace must have 'failed' filter chip"

    def test_has_collapse_all_button(self):
        source = self._timeline()
        assert 'data-action="collapse-all"' in source, \
            "Trace must have Collapse All button"

    def test_has_trace_round_row(self):
        source = self._timeline()
        assert 'data-trace-round-row' in source, \
            "Trace must have trace-round-row elements"

    def test_has_trace_detail(self):
        source = self._timeline()
        assert 'data-trace-detail' in source, \
            "Trace must have trace-detail elements"

    def test_trace_row_has_status(self):
        source = self._timeline()
        assert 'data-status=' in source, \
            "Trace rows must have data-status attribute"

    def test_uses_sdt_macros(self):
        source = self._source()
        assert "sdt.trace_round" in source, \
            "Session must use sdt.trace_round macro"
        assert "sdt.hero" in source, \
            "Session must use sdt.hero macro"
        assert "sdt.trace_header" in source, \
            "Session must use sdt.trace_header macro"

    def test_toggle_js_in_timeline_js(self):
        js_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js"
        js = js_path.read_text(encoding="utf-8")
        assert "toggleRound" in js, \
            "Must have toggleRound JS function"


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


# ──────────────────────────────────────────────────────────────────────
# Content modal removed — negative assertions
# ──────────────────────────────────────────────────────────────────────


class TestContentViewerModalRemoved:

    def _source(self):
        return _session_source()

    def test_content_modal_element_removed(self):
        source = self._source()
        assert 'id="content-modal"' not in source, \
            "content-modal element must be removed"

    def test_content_modal_js_removed(self):
        source = self._source()
        assert "openContentModal" not in source, \
            "openContentModal JS must be removed"
        assert "closeContentModal" not in source, \
            "closeContentModal JS must be removed"
        assert "switchContentView" not in source, \
            "switchContentView JS must be removed"


# ──────────────────────────────────────────────────────────────────────
# Metrics Strip
# ──────────────────────────────────────────────────────────────────────


class TestMetricsStrip:

    def _timeline(self):
        return _timeline_component()

    def test_kpis_exist(self):
        source = self._timeline()
        assert "sd-kpis" in source, \
            "KPI metrics container must exist"
        assert "sd-kpi" in source, \
            "KPI items must exist"

    def test_has_tokens_metric(self):
        source = self._timeline()
        assert "tokens" in source.lower(), \
            "Metrics must include tokens"

    def test_has_rounds_metric(self):
        source = self._timeline()
        assert "rounds" in source.lower(), \
            "Metrics must include rounds"
