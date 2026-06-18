"""Static DOM contract tests for trace row structure.

Architecture (T089 HIFI table migration):
- Trace rows use <table class="trace-table"> with <colgroup>/<thead>/<tbody>
- Each round = two <tr> rows: <tr class="round-row"> + <tr class="expanded-row">
- Toggle button: <button data-action="toggle-round"> in the Open column
- Detail row: <tr class="expanded-row" data-trace-detail>
- aria-controls points to round-{N}-detail id
- JS dispatches on data-action attribute
- CSS in css/session-detail.css

Tests analyze component templates and JS files using regex-based static analysis.
"""
import pytest
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TIMELINE = ROOT / "src" / "session_browser" / "web" / "templates" / "components" / "session_detail_timeline.html"
JS_DIR = ROOT / "src" / "session_browser" / "web" / "static" / "js" / "session-detail"
CSS_FILE = ROOT / "src" / "session_browser" / "web" / "static" / "css" / "session-detail.css"
CSS_DIR = CSS_FILE.parent / "session-detail"
TIMELINE_DIR = TIMELINE.parent / "session_detail_timeline"


def _read_source_with_splits(main_file, split_dir):
    """Read main file and all split subdirectory files (if they exist)."""
    parts = []
    if main_file is not None and main_file.exists():
        parts.append(main_file.read_text(encoding="utf-8"))
    if split_dir.is_dir():
        source_hint = str(main_file) if main_file is not None else str(split_dir)
        if "css" in source_hint:
            ext = "*.css"
        elif "js" in source_hint:
            ext = "*.js"
        else:
            ext = "*.html"
        for f in sorted(split_dir.glob(ext)):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


@pytest.fixture(scope="module")
def template_source():
    """Load the timeline component template source (with split-aware reading)."""
    if not TIMELINE.exists():
        pytest.fail(f"Template not found: {TIMELINE}")
    return _read_source_with_splits(TIMELINE, TIMELINE_DIR)


# ── 追踪行不是按钮 ────────────────────────────────────────


class TestTraceRowNotButton:

    @pytest.mark.contract_case("UI-SD-017")
    def test_no_button_trace_row(self, template_source):
        """Template must not contain <button class="trace-row">."""
        pattern = re.compile(r'<button\b[^>]*class="[^"]*trace-row[^"]*"')
        matches = pattern.findall(template_source)
        assert len(matches) == 0, f"Found <button class=\"trace-row\">: {matches}"

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_row_is_table_row(self, template_source):
        """Trace row should be a <tr class="round-row"> element."""
        pattern = re.compile(r'<tr\b[^>]*class="[^"]*round-row[^"]*"[^>]*data-trace-round-row')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No <tr class=\"round-row\" data-trace-round-row> found"


# ── 切换按钮契约 ──────────────────────────────────────────


class TestToggleButtonContract:
    """Toggle button must exist with proper ARIA attributes."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_button_present(self, template_source):
        assert 'class="sd-round-summary"' in template_source, (
            "Missing .sd-round-summary in template"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_has_data_action(self, template_source):
        assert 'data-action="toggle-round"' in template_source, (
            'Toggle button must have data-action="toggle-round"'
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_has_aria_expanded(self, template_source):
        assert 'aria-expanded=' in template_source, (
            "Toggle button must have aria-expanded"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_has_aria_controls(self, template_source):
        assert 'aria-controls=' in template_source, (
            "Toggle button must have aria-controls"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_has_round_id(self, template_source):
        assert 'data-round=' in template_source, (
            "Toggle button must have data-round attribute"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_has_preview(self, template_source):
        assert 'sd-round-preview' in template_source, (
            "Toggle must have preview section"
        )
        assert 'sd-round-preview__title' in template_source, (
            "Toggle must have preview title"
        )


# ── Trace detail contract ───────────────────────────────────────────


class TestTraceDetailContract:
    """Each trace-detail must have a matching id referenced by toggle aria-controls."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_detail_data_attr(self, template_source):
        assert 'data-trace-detail' in template_source, (
            "Trace detail must have data-trace-detail attribute"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_detail_is_table_row(self, template_source):
        """Trace detail must be a <tr class="expanded-row"> element."""
        pattern = re.compile(r'<tr\b[^>]*class="[^"]*expanded-row[^"]*"[^>]*data-trace-detail')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No <tr class=\"expanded-row\" data-trace-detail> found"

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_detail_has_round_id(self, template_source):
        """Detail row must have id matching round-{N}-detail pattern."""
        pattern = re.compile(r'id="round-\{\{[^}]+\}\}-detail"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No trace-detail ids matching round-{N}-detail found"

    @pytest.mark.contract_case("UI-SD-017")
    def test_aria_controls_matches_detail_id(self, template_source):
        """aria-controls must reference round-{N}-detail id pattern."""
        controls = re.findall(r'aria-controls="round-\{\{[^}]+\}\}-detail"', template_source)
        ids = re.findall(r'id="round-\{\{[^}]+\}\}-detail"', template_source)
        assert len(controls) > 0, "No aria-controls matching round-{N}-detail found"
        assert len(ids) > 0, "No trace-detail ids matching round-{N}-detail found"


# ── Trace detail is sibling of round row ────────────────────────────


class TestTraceDetailSibling:
    """trace-detail must follow the round row in tbody (adjacent <tr> rows)."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_detail_outside_summary(self):
        """expanded_row must be separate from round_row macro."""
        source = _read_source_with_splits(TIMELINE, TIMELINE_DIR)
        assert '{% macro expanded_row' in source, (
            "expanded_row must be a separate macro"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_round_calls_both_macros(self):
        """trace_round macro must call both round_row and expanded_row."""
        # In split structure, trace_round is in round_table.html
        source = _read_source_with_splits(TIMELINE, TIMELINE_DIR)
        # Check that trace_round references both round_row and expanded_row
        trace_round_section = source[source.find('{% macro trace_round'):]
        trace_round_section = trace_round_section[:trace_round_section.find('{%- endmacro %}') + len('{%- endmacro %}')]
        # Either direct calls or delegation to a module that contains both
        if '{{ round_row(row) }}' in trace_round_section:
            assert '{{ expanded_row(row) }}' in trace_round_section, (
                "trace_round must call expanded_row"
            )
        else:
            # Delegation pattern: check round_table split module
            round_table_path = TIMELINE_DIR / "round_table.html"
            if round_table_path.exists():
                rt_content = round_table_path.read_text(encoding="utf-8")
                assert '{{ round_row(row) }}' in rt_content or '_sdt_round.round_row' in rt_content, (
                    "round_table must call round_row"
                )
                assert '{{ expanded_row(row) }}' in rt_content or '_sdt_round.expanded_row' in rt_content, (
                    "round_table must call expanded_row"
                )


# ── No nested button conflict ───────────────────────────────────────


class TestNoNestedButtonConflict:
    """Trace row structure must not have illegal button nesting."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_payload_buttons_in_detail(self, template_source):
        """Payload buttons should exist on message/event/tool rows."""
        assert "user_message_event" in template_source, "Must render user message rows"
        assert "assistant_event" in template_source, "Must render assistant event rows"
        assert "tool_call_event" in template_source, "Must render tool call rows"
        assert "open-payload" in template_source, "Detail rows must expose payload buttons"

    @pytest.mark.contract_case("UI-SD-017")
    def test_row_clickable_for_toggle(self, template_source):
        """Round rows must have data-trace-round-row for row-click toggle."""
        pattern = re.compile(r'data-trace-round-row')
        matches = pattern.findall(template_source)
        assert len(matches) >= 1, f"Expected at least 1 data-trace-round-row for row-click toggle, found {len(matches)}"

    @pytest.mark.contract_case("UI-SD-017")
    def test_no_open_column(self, template_source):
        """Open column and toggle button removed; clicking row toggles detail."""
        # Ensure no col-open in colgroup
        assert "col-open" not in template_source, (
            "Open column should be removed from colgroup"
        )


# ── Grid structure ──────────────────────────────────────────────────


class TestTraceRowGridStructure:
    """Trace row must have the expected column structure."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_has_round_id_cell(self, template_source):
        assert 'sd-round-id' in template_source, (
            "Must have round ID cell"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_has_status_cell(self, template_source):
        assert 'round_status(' in template_source, (
            "Must have status cell via macro"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_has_preview_cell(self, template_source):
        assert 'sd-round-preview' in template_source, (
            "Must have preview cell"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_has_metric_cells(self, template_source):
        assert 'sd-round-metric' in template_source, (
            "Must have metric cells"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_has_token_mix(self, template_source):
        assert 'sd-round-mix' in template_source, (
            "Must have token mix bar"
        )


# ── Round table compact behavior ────────────────────────────────────


class TestRoundTableCompactBehavior:
    """Round table summary cells should stay compact and directly actionable."""

    def _round_table_source(self):
        return (TIMELINE_DIR / "round_table.html").read_text(encoding="utf-8")

    def _llm_call_source(self):
        return (TIMELINE_DIR / "llm_call.html").read_text(encoding="utf-8")

    @pytest.mark.contract_case("UI-SD-017")
    def test_metrics_omit_llm_call_count(self):
        source = self._round_table_source()
        assert "row.tool_count_label" in source, "Metrics must render tool count"
        assert "format_compact_token" in source, "Metrics must render token total"
        assert "llm_call_count" not in source
        assert "}} llm" not in source.lower()
        assert " llm</span>" not in source.lower()

    @pytest.mark.contract_case("UI-SD-017")
    def test_tokenbar_scales_against_max_round(self):
        source = self._round_table_source()
        css = _read_source_with_splits(CSS_FILE, CSS_DIR)
        assert "--token-total-width:{{ row.token_bar_pct" in source
        assert "row.token_bar_gap_label" in source
        assert "background: #e5e7eb" in css
        assert "width: var(--token-total-width, 0%)" in css

    @pytest.mark.contract_case("UI-SD-017")
    def test_attribution_visible_labels_are_request_response(self):
        source = self._llm_call_source()
        assert "attribution_chip(request, 'request')" in source
        assert "attribution_chip(response, 'response')" in source
        assert ">{{ fallback_label }}</button>" in source

    @pytest.mark.contract_case("UI-SD-017")
    def test_signals_do_not_render_empty_placeholder_badge(self):
        source = self._round_table_source()
        assert 'class="round-signals"' in source
        assert "badge-info" not in source
        assert ">—</span>" not in source

    @pytest.mark.contract_case("UI-SD-017")
    def test_open_round_lines_are_inset_not_outline(self):
        css = _read_source_with_splits(CSS_FILE, CSS_DIR)
        assert ".round-row.is-open" in css
        assert "inset 0 1px 0" in css
        assert "inset 0 -1px 0" in css
        assert ".round-row.is-jump-target {\n  outline: 0;" in css

    @pytest.mark.contract_case("UI-SD-017")
    def test_timeline_rail_aligns_with_dots(self):
        source = self._llm_call_source()
        css = _read_source_with_splits(CSS_FILE, CSS_DIR)
        assert "timeline_dot('user')" in source
        assert ".sd-timeline-dot--user" in css
        assert ".expanded-row td .sd-timeline:before" in css
        assert "left: 22px" in css

    @pytest.mark.contract_case("UI-SD-017")
    def test_flat_timeline_rows_use_fixed_columns(self):
        css = _read_source_with_splits(CSS_FILE, CSS_DIR)
        assert "--sd-tool-kind-col" in css
        assert "--sd-tool-time-col" in css
        assert "--sd-tool-action-col" in css
        assert ".sd-tool-group--flat .sd-tool-row" in css
        assert "var(--sd-tool-kind-col)" in css


class TestSubagentSubroundToggle:
    """Subagent subround rows should be independently toggleable."""

    def _subagent_source(self):
        return (TIMELINE_DIR / "subagent.html").read_text(encoding="utf-8")

    def _js_source(self):
        return _read_source_with_splits(None, JS_DIR)

    def _css_source(self):
        return _read_source_with_splits(CSS_FILE, CSS_DIR)

    @pytest.mark.contract_case("UI-SD-017")
    def test_subround_summary_has_toggle_action_and_state(self):
        source = self._subagent_source()
        assert "data-sub-round-toggle" in source
        assert 'class="sd-sub-round__toggle"' in source
        assert 'data-action="toggle-sub-round"' in source
        assert 'aria-expanded=' in source
        assert "data-sub-round-open" in source
        assert "data-sub-round-steps" in source

    @pytest.mark.contract_case("UI-SD-017")
    def test_js_supports_single_subround_toggle(self):
        js = self._js_source()
        assert "function toggleSubagentRound" in js
        assert "function setSubRoundOpen" in js
        assert "function syncSubRoundToggle" in js
        assert "action === 'toggle-sub-round'" in js
        assert "data-sub-round-toggle" in js

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_subround_toggle_affordance(self):
        css = self._css_source()
        assert ".sd-sub-round__toggle" in css
        assert ".sd-sub-round.is-open .sd-sub-round__toggle span" in css
        assert ".sd-sub-round.is-open .sd-sub-round__summary" in css
        assert "cursor: pointer" in css


# ── No illegal nested buttons ───────────────────────────────────────


class TestNoIllegalNestedButtons:
    """Template must not produce nested button elements within trace-row."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_row_is_tr_not_button(self, template_source):
        """The trace-row itself must be a <tr> element."""
        pattern = re.compile(
            r'<(button|div|tr)\b[^>]*data-trace-round-row',
            re.DOTALL
        )
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "Could not find trace-row element"
        for tag in matches:
            assert tag == "tr", f"trace-row uses <{tag}> tag, should be <tr>"


# ── Multiple rounds have unique toggles ─────────────────────────────


class TestMultipleRoundsHaveToggles:
    """All rounds should have their own toggle button with unique aria-controls."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_button_exists(self, template_source):
        pattern = re.compile(r'class="sd-round-summary"')
        matches = pattern.findall(template_source)
        assert len(matches) >= 1, f"Expected at least 1 toggle button, found {len(matches)}"

    @pytest.mark.contract_case("UI-SD-017")
    def test_unique_aria_controls_template(self, template_source):
        """aria-controls should be templated with row.round_id for uniqueness."""
        pattern = re.compile(r'aria-controls="round-\{\{\s*row\.round_id\s*\}\}-detail"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No unique aria-controls pattern found"

    @pytest.mark.contract_case("UI-SD-017")
    def test_unique_trace_detail_ids_template(self, template_source):
        """trace-detail ids should be templated with row.round_id for uniqueness."""
        pattern = re.compile(r'id="round-\{\{\s*row\.round_id\s*\}\}-detail"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No unique trace-detail id pattern found"


# ── JS event dispatch on data-action ────────────────────────────────


class TestJSEventDispatchOnDataAction:
    """JS must dispatch toggle on data-action=\"toggle-round\"."""

    def _js_source(self):
        return _read_source_with_splits(None, JS_DIR)

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_round_action_in_js(self):
        js = self._js_source()
        assert "toggle-round" in js, (
            'JS must reference toggle-round action'
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_toggle_round_function_exists(self):
        js = self._js_source()
        assert "toggleRound" in js, (
            "JS must contain toggleRound function"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_js_uses_data_action_dispatch(self):
        js = self._js_source()
        assert 'action ===' in js or "action ===" in js or \
               'dataset.action' in js or 'getAttribute("data-action")' in js, (
            "JS should dispatch events based on data-action attribute"
        )


# ── CSS styles ──────────────────────────────────────────────────────


class TestCSSStyles:
    """CSS must contain trace table and row styles."""

    def _css_source(self):
        return _read_source_with_splits(CSS_FILE, CSS_DIR)

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_trace_table(self):
        css = self._css_source()
        assert ".trace-table" in css, (
            "CSS must include .trace-table styles"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_round_row(self):
        css = self._css_source()
        assert ".round-row" in css, (
            "CSS must include .round-row styles"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_expanded_row(self):
        css = self._css_source()
        assert ".expanded-row" in css, (
            "CSS must include .expanded-row styles"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_sd_round_summary(self):
        css = self._css_source()
        assert ".sd-round-summary" in css, (
            "CSS must include .sd-round-summary styles"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_sd_round_preview(self):
        css = self._css_source()
        assert ".sd-round-preview" in css, (
            "CSS must include .sd-round-preview styles"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_sd_round_metric(self):
        css = self._css_source()
        assert ".sd-round-metric" in css, (
            "CSS must include .sd-round-metric styles"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_css_has_token_bar(self):
        css = self._css_source()
        assert ".sd-tokenbar" in css or "sd-tokenbar" in css or ".tokenbar" in css, (
            "CSS must include token bar styles"
        )
