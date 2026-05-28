"""Static DOM contract tests for v18 trace row structure.

v18 architecture (T089 HIFI table migration):
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
JS_FILE = ROOT / "src" / "session_browser" / "web" / "static" / "js" / "session-detail.js"
CSS_FILE = ROOT / "src" / "session_browser" / "web" / "static" / "css" / "session-detail.css"


@pytest.fixture(scope="module")
def template_source():
    """Load the timeline component template source."""
    if not TIMELINE.exists():
        pytest.skip(f"Template not found: {TIMELINE}")
    return TIMELINE.read_text(encoding="utf-8")


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
        """v18: trace-row should be a <tr class="round-row"> element."""
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
        """v18: Trace detail must be a <tr class="expanded-row"> element."""
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
    def test_detail_outside_summary(self, template_source):
        """expanded_row must be separate from round_row macro."""
        assert '{% macro expanded_row' in template_source, (
            "expanded_row must be a separate macro"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_trace_round_calls_both_macros(self, template_source):
        """trace_round macro must call both round_row and expanded_row."""
        trace_round_block = template_source[template_source.find('{% macro trace_round'):]
        trace_round_block = trace_round_block[:trace_round_block.find('{%- endmacro %}') + len('{%- endmacro %}')]
        assert '{{ round_row(row) }}' in trace_round_block, (
            "trace_round must call round_row"
        )
        assert '{{ expanded_row(row) }}' in trace_round_block, (
            "trace_round must call expanded_row"
        )


# ── No nested button conflict ───────────────────────────────────────


class TestNoNestedButtonConflict:
    """Trace row structure must not have illegal button nesting."""

    @pytest.mark.contract_case("UI-SD-017")
    def test_payload_buttons_in_detail(self, template_source):
        """Payload buttons should be invoked inside detail context (llm_call_card, tool_batch)."""
        # v9 uses sdp.button() macro calls with 'open-payload' action; Request renamed from Context
        assert "sdp.button('Request'" in template_source or "'Request'" in template_source, (
            "Must have Request button in detail"
        )
        assert "sdp.button('Response'" in template_source or "'Response'" in template_source, (
            "Must have Response button in detail"
        )

    @pytest.mark.contract_case("UI-SD-017")
    def test_row_clickable_for_toggle(self, template_source):
        """v18: round rows must have data-trace-round-row for row-click toggle."""
        pattern = re.compile(r'data-trace-round-row')
        matches = pattern.findall(template_source)
        assert len(matches) >= 1, f"Expected at least 1 data-trace-round-row for row-click toggle, found {len(matches)}"

    @pytest.mark.contract_case("UI-SD-017")
    def test_no_open_column(self, template_source):
        """v18: open column and toggle button removed; clicking row toggles detail."""
        # Ensure no col-open in colgroup
        assert "col-open" not in template_source, (
            "Open column should be removed from colgroup"
        )


# ── Grid structure ──────────────────────────────────────────────────


class TestTraceRowGridStructure:
    """v9 trace row must have the expected column structure."""

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
        if not JS_FILE.exists():
            pytest.skip(f"JS file not found: {JS_FILE}")
        return JS_FILE.read_text(encoding="utf-8")

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
    """CSS must contain v18 trace table and row styles."""

    def _css_source(self):
        if not CSS_FILE.exists():
            pytest.skip(f"CSS not found: {CSS_FILE}")
        return CSS_FILE.read_text(encoding="utf-8")

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
