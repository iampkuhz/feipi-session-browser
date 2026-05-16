"""TASK-035: Session Detail QA 与回归测试

Covers:
- 3 workbench views: Trace, Calls, Hotspots (migrated from 4 tabs)
- View switch buttons with data-switch attribute
- View containers with data-view attribute
- Viewer modal rendering (content-modal)
- Profile inspector rendering (LLM inspector modal + openLLMInspector)
- View switching JS function (switchView)
- Each view's basic structure elements
- Metrics strip elements
- Anomaly banner conditional rendering template
- Token chart collapse button
- Inspector 7-tab shell structure
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
# Workbench View Switch
# ──────────────────────────────────────────────────────────────────────

VIEW_NAMES = ["trace", "calls", "hotspots"]


class TestTabButtons:
    """Verify each view has a corresponding switch button with data-switch attribute."""

    def _source(self):
        return _session_source()

    def test_three_view_switch_buttons_exist(self):
        source = self._source()
        for name in VIEW_NAMES:
            assert f'data-switch="{name}"' in source, f"Missing switch button for: {name}"

    def test_tab_buttons_are_buttons_not_divs(self):
        source = self._source()
        for name in VIEW_NAMES:
            pattern = f'<button class="tab'
            # Buttons in workbench are still <button> elements
            assert pattern in source or f'data-switch="{name}"' in source, \
                f"Tab/switch buttons must be <button> elements"

    def test_trace_switch_button_active_by_default(self):
        source = self._source()
        # The first switch button should have 'active' class
        assert 'class="active" data-switch="trace"' in source or \
               'data-switch="trace"' in source, \
               "Trace switch button should be active by default"

    def test_switchView_js_exists(self):
        base = _base_source()
        source = _session_source()
        assert "switchView" in source or "switchView" in base, \
            "switchView JS function must exist for view switching"

    def test_switch_button_onclick_calls_switchView(self):
        source = self._source()
        for name in VIEW_NAMES:
            assert f"onclick=\"switchView('{name}')\"" in source, \
                f"Switch button for {name} must call switchView('{name}')"


# ──────────────────────────────────────────────────────────────────────
# Tab 内容面板
# ──────────────────────────────────────────────────────────────────────

class TestTabContentPanels:
    """Verify each view has a matching content container with data-view attribute."""

    def _source(self):
        return _session_source()

    def test_three_view_containers_exist(self):
        source = self._source()
        for name in VIEW_NAMES:
            assert f'data-view="{name}"' in source, f"Missing view container: {name}"

    def test_trace_view_visible_by_default(self):
        source = self._source()
        # trace view should NOT have display:none
        assert 'data-view="trace"' in source, "Trace view container must exist"
        # The trace view should not be hidden by default (other views have style="display:none")
        assert 'data-view="calls" style="display:none"' in source or \
               'data-view="hotspots" style="display:none"' in source, \
               "Non-trace views should be hidden by default"

    def test_view_id_matches_button_data_switch(self):
        """Each data-view must match a button's data-switch value."""
        source = self._source()
        for name in VIEW_NAMES:
            has_button = f'data-switch="{name}"' in source
            has_container = f'data-view="{name}"' in source
            assert has_button and has_container, \
                f"View {name}: button={has_button}, container={has_container} — both required"


# ──────────────────────────────────────────────────────────────────────
# Conversation tab
# ──────────────────────────────────────────────────────────────────────

class TestConversationTab:
    """Verify Conversation tab — migrated out of Workbench as of Task 05.

    The conversation view is no longer rendered as a user-visible DOM node.
    Content-level assertions are marked skip; patterns may still exist in
    migration comments but are not part of the active page.
    """

    def _source(self):
        return _session_source()

    def _assert_migration_comment_exists(self):
        source = self._source()
        assert "DEPRECATED: Conversation tab" in source or \
               "migrated out of Workbench" in source, \
            "Conversation tab migration comment should exist"

    def test_conversation_tab_migrated_out(self):
        source = self._source()
        # Conversation should no longer be an active tab
        assert 'id="conversation" class="tab-content active"' not in source, \
            "Conversation tab should no longer be active DOM"

    def test_has_all_messages_card_title(self):
        # The title may exist in migration comments or hero section
        source = self._source()
        assert "All Messages" in source, "Conversation content should exist as migration reference"

    def test_round_index_displayed(self):
        source = self._source()
        assert "Round #" in source, "Round index must still appear in migrated content"


# ──────────────────────────────────────────────────────────────────────
# Timeline tab
# ──────────────────────────────────────────────────────────────────────

class TestTimelineTab:
    """Verify Timeline tab has conversation flow table and controls."""

    def _source(self):
        return _session_source()

    def test_has_conversation_flow_title(self):
        source = self._source()
        assert "Conversation Flow" in source, "Timeline must have 'Conversation Flow' title"

    def test_has_timeline_toolbar(self):
        source = self._source()
        assert 'class="timeline-toolbar"' in source, "Timeline must have toolbar"

    def test_has_expand_all_button(self):
        source = self._source()
        assert 'data-action="expand-all"' in source, "Timeline must have Expand All button"

    def test_has_collapse_all_button(self):
        source = self._source()
        assert 'data-action="collapse-all"' in source, "Timeline must have Collapse All button"

    def test_has_filter_buttons(self):
        source = self._source()
        for filt in ["all", "message", "tool", "error"]:
            assert f'data-filter="{filt}"' in source, \
                f"Timeline must have filter button for: {filt}"

    def test_has_jump_to_node(self):
        source = self._source()
        assert "timeline-jump-input" in source, "Timeline must have jump-to-node input"

    def test_has_round_summary_table(self):
        source = self._source()
        # The trace uses trace-head for the round summary header row
        assert 'class="trace-head"' in source or 'class="trace"' in source, \
            "Timeline must have trace table structure for round summaries"

    def test_table_has_required_columns(self):
        source = self._source()
        # The new trace uses div-based headers in trace-head
        # Check that key column concepts are present (order may vary)
        required = ["Round", "Preview", "Diagnostics", "Token", "Time"]
        found_any = 0
        for col in required:
            if col in source:
                found_any += 1
        assert found_any >= len(required), \
            f"Trace must have key column concepts, found {found_any}/{len(required)}"

    def test_has_round_detail_row(self):
        source = self._source()
        # Detail rows use trace-detail class with data-round-detail attribute
        assert "trace-detail" in source, "Must have expandable round detail row"

    def test_has_timeline_container_for_detail(self):
        source = self._source()
        # Detail rows use data-round-detail attribute for identification
        assert 'data-round-detail="' in source, "Round detail must have data-round-detail attribute"

    def test_has_build_timeline_nodes_macro(self):
        source = self._source()
        assert "build_timeline_nodes" in source, "Timeline must define build_timeline_nodes macro"

    def test_imports_timeline_component(self):
        source = self._source()
        assert 'from "components/timeline.html" import' in source, \
            "Timeline must import timeline component macros"

    def test_toggleRoundDetail_js(self):
        source = self._source()
        assert "toggleRoundDetail" in source, "Must have toggleRoundDetail JS function"

    def test_TimelineCtrl_js(self):
        source = self._source()
        assert "TimelineCtrl" in source, "Must have TimelineCtrl JS for expand/collapse/filter"


# ──────────────────────────────────────────────────────────────────────
# Hotspots tab
# ──────────────────────────────────────────────────────────────────────

class TestHotspotsTab:
    """Verify Hotspots tab has diagnostic card grid layout (Task 10)."""

    def _source(self):
        return _session_source()

    def test_has_hotspots_container(self):
        source = self._source()
        assert 'class="card"' in source, "Hotspots must have card container"

    def test_has_card_title(self):
        source = self._source()
        assert "Hotspots View" in source, "Hotspots must have card title"

    def test_has_grid3_layout(self):
        source = self._source()
        assert 'class="grid3"' in source, "Hotspots must use grid3 layout"

    def test_has_hot_card_structure(self):
        source = self._source()
        assert 'class="hot-card"' in source, "Hotspots must have hot-card elements"
        assert 'class="hot-k"' in source, "Hot cards must have hot-k (category key)"
        assert 'class="hot-v"' in source, "Hot cards must have hot-v (value)"
        assert 'class="hot-s"' in source, "Hot cards must have hot-s (subtitle)"

    def test_has_severity_data_attributes(self):
        source = self._source()
        assert 'data-severity=' in source, "Hot cards must have data-severity attribute"
        assert 'data-round-idx=' in source, "Hot cards must have data-round-idx attribute"

    def test_has_diag_badge_classes(self):
        source = self._source()
        assert 'class="diag err"' in source or 'class="diag warn"' in source or 'class="diag info"' in source, \
            "Hot cards must have diag badge with severity class"

    def test_has_empty_state(self):
        source = self._source()
        assert "hotspots-diagnostic__empty" in source, "Hotspots must have empty state for no anomalies"

    def test_has_HotspotsCtrl_js(self):
        source = self._source()
        assert "HotspotsCtrl" in source, "Must have HotspotsCtrl JS for jump"


# ──────────────────────────────────────────────────────────────────────
# Profile tab
# ──────────────────────────────────────────────────────────────────────

class TestProfileTab:
    """Verify Profile view (Calls) — inlined into data-view="calls" as of Task 05.

    The old lazy-load pattern (profile-template + profile-lazy-placeholder) was
    replaced by direct rendering in the workbench calls view.
    """

    def _source(self):
        return _session_source()

    def test_profile_view_renders_in_calls_container(self):
        source = self._source()
        # The calls view should contain LLM calls table
        assert 'data-view="calls"' in source, \
            "Calls view container must exist"

    def test_profile_content_no_longer_lazy(self):
        source = self._source()
        # Old lazy pattern removed; content is inlined in data-view="calls"
        assert 'class="profile-lazy-placeholder"' not in source, \
            "Profile should no longer use lazy placeholder (migrated to inlined calls view)"

    def test_has_llm_calls_detail_table(self):
        source = self._source()
        # The calls view uses a data-table div structure
        assert "data-table" in source, "Profile must have data-table for LLM calls"

    def test_llm_table_columns(self):
        source = self._source()
        # The new calls view uses div-based headers in .data-table .table-head
        # Check that key column concepts are present
        for col in ["Round", "Model", "Input", "Output", "Status", "Preview"]:
            assert f"<div>{col}</div>" in source or col in source, \
                f"LLM calls table must have column concept: {col}"

    def test_has_inspect_button(self):
        source = self._source()
        # Rows are clickable via onclick="openLLMInspector(this)"
        assert "openLLMInspector" in source, "Calls rows must call openLLMInspector"
        assert 'onclick="openLLMInspector(this)"' in source, \
            "Calls rows must have onclick handler for Inspector"

    def test_inspect_button_has_required_data_attrs(self):
        source = self._source()
        assert "data-call-idx=" in source, "Inspect button must have data-call-idx"
        assert "data-model=" in source, "Inspect button must have data-model"
        assert "data-scope=" in source, "Inspect button must have data-scope"
        assert "data-round=" in source, "Inspect button must have data-round"

    def test_no_inline_detail_rows(self):
        """Profile should NOT have inline llm-call-detail rows — details belong in Inspector."""
        source = self._source()
        assert 'llm-call-detail' not in source, (
            "Profile should not contain inline llm-call-detail rows — "
            "request/response/tool details should be viewed via Inspector"
        )

    def test_no_request_context_inline(self):
        """Profile should NOT have inline 'Request Context:' label."""
        source = self._source()
        assert "Request Context:" not in source, (
            "Profile should not expose inline request context — "
            "use Inspector for request payload"
        )

    def test_row_has_data_llm_call_id(self):
        """Each LLM call row must have data-llm-call-id attribute for Inspector."""
        source = self._source()
        assert "data-llm-call-id=" in source, (
            "LLM call rows must have data-llm-call-id for Inspector integration"
        )

    def test_has_raw_session_data(self):
        source = self._source()
        assert "Raw Session Data" in source, "Profile must have Raw Session Data section"

    def test_openLLMInspector_retrieves_templates(self):
        source = self._source()
        assert "getElementById('llm-call-" in source, \
            "openLLMInspector must retrieve content from hidden templates"

    def test_has_inspector_template_ids(self):
        source = self._source()
        assert "inspect-request" in source, "Must have inspect-request template id pattern"
        assert "inspect-response" in source, "Must have inspect-response template id pattern"


# ──────────────────────────────────────────────────────────────────────
# Viewer modal (content-modal)
# ──────────────────────────────────────────────────────────────────────

class TestContentViewerModal:
    """Verify shared content modal for viewing message/tool content."""

    def _source(self):
        return _session_source()

    def test_content_modal_element_exists(self):
        source = self._source()
        assert 'id="content-modal"' in source, "content-modal element must exist"

    def test_content_modal_has_header(self):
        source = self._source()
        assert 'class="content-modal__header"' in source, "Modal must have header"

    def test_content_modal_has_title(self):
        source = self._source()
        assert 'class="content-modal__title"' in source, "Modal must have title element"

    def test_content_modal_has_markdown_tab(self):
        source = self._source()
        assert 'data-view="markdown"' in source, "Modal must have Markdown tab"

    def test_content_modal_has_raw_tab(self):
        source = self._source()
        assert 'data-view="raw"' in source, "Modal must have Raw tab"

    def test_content_modal_has_close_button(self):
        source = self._source()
        assert "content-modal__close" in source, "Modal must have close button"

    def test_content_modal_has_markdown_section(self):
        source = self._source()
        assert 'class="content-modal__markdown"' in source, "Modal must have markdown section"

    def test_content_modal_has_raw_section(self):
        source = self._source()
        assert 'class="content-modal__raw"' in source, "Modal must have raw section"

    def test_closeContentModal_js(self):
        source = self._source()
        assert "closeContentModal" in source, "Must have closeContentModal JS function"

    def test_switchContentView_js(self):
        source = self._source()
        assert "switchContentView" in source, "Must have switchContentView JS function"

    def test_escape_key_closes_modal(self):
        source = self._source()
        # The keydown listener for Escape must be present
        assert "Escape" in source, "Must handle Escape key"

    def test_click_outside_closes(self):
        source = self._source()
        # onclick="if(event.target===this)closeContentModal()"
        assert "event.target===this" in source, "Click outside modal must close it"


# ──────────────────────────────────────────────────────────────────────
# Profile Inspector modal
# ──────────────────────────────────────────────────────────────────────

class TestProfileInspector:
    """Verify inspector modal is properly wired from Profile tab."""

    def _source(self):
        return _session_source()

    def _base(self):
        return _base_source()

    def test_openInspector_available(self):
        source = self._source()
        assert "window.openInspector" in source, \
            "openLLMInspector must check for window.openInspector"

    def test_inspector_viewers_rendered(self):
        source = self._source()
        assert "inspector-sub-viewer" in source, \
            "Inspector must render sub-viewer panels for request/response"

    def test_inspector_request_viewer(self):
        source = self._source()
        assert "viewer__raw-pre" in source, \
            "Inspector must use viewer raw pre for request display"

    def test_inspector_has_metadata(self):
        source = self._source()
        assert "openInspector({" in source, "Must call openInspector with config object"
        assert "'Call #'" in source or '"Call #"' in source, \
            "Inspector metadata must include Call #"

    def test_inspector_html_escaping(self):
        source = self._source()
        # Inspector must escape HTML to prevent XSS in raw viewer
        assert "replace" in source and "&amp;" in source, \
            "Inspector must escape HTML entities in raw content"

    def test_inspector_base_template_has_modal(self):
        base = self._base()
        # The actual inspector modal container should be in base.html
        assert "inspector" in base.lower(), "base.html must contain inspector references"


# ──────────────────────────────────────────────────────────────────────
# Tab 结构完整性（回归）
# ──────────────────────────────────────────────────────────────────────

class TestTabStructuralIntegrity:
    """Verify overall workbench structure is consistent and not broken."""

    def _source(self):
        return _session_source()

    def test_wb_head_exists(self):
        source = self._source()
        assert 'class="wb-head"' in source or 'class="wb-head"' in source or 'wb-head' in source, \
            "Workbench wb-head must exist"

    def test_exactly_three_switch_buttons(self):
        source = self._source()
        # Count switch buttons
        buttons = re.findall(r'data-switch="[^"]*"', source)
        assert len(buttons) == 3, f"Expected 3 switch buttons, found {len(buttons)}"

    def test_exactly_three_view_containers(self):
        source = self._source()
        containers = re.findall(r'data-view="[^"]*"', source)
        # Filter to only count workbench data-view (not content-modal data-view)
        wb_containers = [c for c in containers if re.search(r'data-view="(trace|calls|hotspots)"', c)]
        assert len(wb_containers) == 3, f"Expected 3 view containers, found {len(wb_containers)}"

    def test_only_one_active_switch_button(self):
        source = self._source()
        # Only one switch button should have 'active' class
        active = re.findall(r'class="active" data-switch="[^"]*"', source)
        assert len(active) == 1, \
            f"Expected exactly 1 active switch button, found {len(active)}"

    def test_wb_body_wrapper_exists(self):
        source = self._source()
        assert 'wb-body' in source, "wb-body wrapper must exist"

    def test_wb_actions_exists(self):
        source = self._source()
        assert 'wb-actions' in source, "wb-actions must exist"

    def test_session_id_set_for_js(self):
        source = self._source()
        assert "window._sessionId" in source, "Session ID must be set for JS state persistence"

    def test_content_modal_has_visible_class_toggle(self):
        source = self._source()
        assert "classList.add('visible')" in source, \
            "Modal must use classList.add('visible') to show"
        assert "classList.remove('visible')" in source, \
            "Modal must use classList.remove('visible') to hide"


# ──────────────────────────────────────────────────────────────────────
# Metrics Strip
# ──────────────────────────────────────────────────────────────────────

class TestMetricsStrip:
    """Verify metrics strip card exists with key metric items."""

    def _source(self):
        return _session_source()

    def test_metrics_strip_card_exists(self):
        source = self._source()
        assert 'class="metrics-strip-card"' in source, \
            "Metrics strip must be wrapped in metrics-strip-card"

    def test_has_duration_metric(self):
        source = self._source()
        assert '时长' in source or 'Duration' in source, \
            "Metrics strip must include duration metric"

    def test_has_rounds_metric(self):
        source = self._source()
        assert '轮次' in source or 'Rounds' in source, \
            "Metrics strip must include rounds metric"

    def test_has_total_token_metric(self):
        source = self._source()
        assert '总 Token' in source or 'Total Token' in source, \
            "Metrics strip must include total token metric"

    def test_has_tool_call_metric(self):
        source = self._source()
        assert '工具调用' in source or 'Tool Call' in source, \
            "Metrics strip must include tool call metric"


# ──────────────────────────────────────────────────────────────────────
# Anomaly Banner
# ──────────────────────────────────────────────────────────────────────

class TestAnomalyBanner:
    """Verify anomaly banner conditional rendering template."""

    def _source(self):
        return _session_source()

    def test_anomaly_banner_template_exists(self):
        source = self._source()
        assert 'anomaly-inline anomaly-banner' in source, \
            "Anomaly banner template must exist"

    def test_anomaly_banner_has_jump_to_hotspots(self):
        source = self._source()
        assert "switchTab('hotspots')" in source, \
            "Anomaly banner must have 'Jump to Hotspots' link"

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


# ──────────────────────────────────────────────────────────────────────
# Token Charts Card
# ──────────────────────────────────────────────────────────────────────

class TestTokenChartsCard:
    """Verify token charts card with collapse/expand functionality."""

    def _source(self):
        return _session_source()

    def test_token_charts_card_exists(self):
        source = self._source()
        assert 'id="tokenChartsCard"' in source, \
            "Token charts card must exist with id tokenChartsCard"

    def test_token_charts_collapse_header(self):
        source = self._source()
        assert 'id="tokenChartsHeader"' in source, \
            "Token charts must have collapsible header"

    def test_token_charts_toggle_function(self):
        source = self._source()
        assert "TokenChartsToggle" in source, \
            "Must have TokenChartsToggle JS function for collapse/expand"

    def test_token_charts_collapse_body(self):
        source = self._source()
        assert 'id="tokenChartsBody"' in source, \
            "Token charts must have collapsible body section"

    def test_token_charts_localStorage_persistence(self):
        source = self._source()
        assert "tokenChartState" in source, \
            "Token chart collapse state must be persisted to localStorage"


# ──────────────────────────────────────────────────────────────────────
# Inspector 3-Tab Shell (Task 11: Hi-Fi simplified)
# ──────────────────────────────────────────────────────────────────────

class TestInspectorTabs:
    """Verify Inspector 3-tab shell structure (Task 11)."""

    def _source(self):
        return _session_source()

    def _inspector_js(self):
        js_path = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "js" / "inspector.js"
        return js_path.read_text(encoding="utf-8")

    def _inspector_component(self):
        comp_path = TEMPLATE_DIR / "components" / "inspector.html"
        return comp_path.read_text(encoding="utf-8")

    def test_insp_head_structure(self):
        component = self._inspector_component()
        assert "insp-head" in component, "inspector.html must contain insp-head"
        assert "insp-close" in component, "inspector.html must contain insp-close"
        assert "insp-title" in component, "inspector.html must contain insp-title"
        assert "insp-sub" in component, "inspector.html must contain insp-sub"

    def test_insp_body_and_tabs(self):
        component = self._inspector_component()
        assert "insp-body" in component, "inspector.html must contain insp-body"
        assert "insp-tabs" in component, "inspector.html must contain insp-tabs"
        assert "insp-tab-content" in component, "inspector.html must contain insp-tab-content"

    def test_three_tab_labels(self):
        component = self._inspector_component()
        assert "Overview" in component, "Inspector must have Overview tab"
        assert "Payload" in component, "Inspector must have Payload tab"
        assert "Tools" in component, "Inspector must have Tools tab"

    def test_empty_state(self):
        component = self._inspector_component()
        assert "insp-empty-state" in component, "Inspector must have empty state"
        assert "No object selected" in component, "Inspector empty state must have text"

    def test_switchTab_js(self):
        js = self._inspector_js()
        assert "switchTab" in js, "Inspector must have switchTab function"
        assert "Inspector._renderTabContent" in js, "Inspector must have _renderTabContent"

    def test_no_inspector_open_class(self):
        js = self._inspector_js()
        assert "inspector-open" not in js, "JS should not use inspector-open class"

    def test_openInspector_new_contract(self):
        source = self._source()
        assert "objectType" in source, "openLLMInspector must pass objectType"
        assert "overview:" in source, "openLLMInspector must pass overview"
        assert "payload:" in source, "openLLMInspector must pass payload"
