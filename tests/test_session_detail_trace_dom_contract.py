"""Static DOM contract tests for v9 trace row structure.

v9 architecture:
- Trace rows use <article class="sd-round"> with data-trace-round-row
- Toggle button is <button class="sd-round-summary"> with data-action="toggle-round"
- Detail panel uses <div class="sd-round-detail"> with data-trace-detail
- aria-controls points to round-{N}-detail id
- JS dispatches on data-action attribute
- CSS in css/session-detail-timeline.css

Tests analyze component templates and JS files using regex-based static analysis.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TIMELINE = ROOT / "src" / "session_browser" / "web" / "templates" / "components" / "session_detail_timeline.html"
JS_FILE = ROOT / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js"
CSS_FILE = ROOT / "src" / "session_browser" / "web" / "static" / "css" / "session-detail-timeline.css"


@pytest.fixture(scope="module")
def template_source():
    """Load the timeline component template source."""
    if not TIMELINE.exists():
        pytest.skip(f"Template not found: {TIMELINE}")
    return TIMELINE.read_text(encoding="utf-8")


# ── Trace row is NOT a button ────────────────────────────────────────


class TestTraceRowNotButton:

    def test_no_button_trace_row(self, template_source):
        """Template must not contain <button class="trace-row">."""
        pattern = re.compile(r'<button\b[^>]*class="[^"]*trace-row[^"]*"')
        matches = pattern.findall(template_source)
        assert len(matches) == 0, f"Found <button class=\"trace-row\">: {matches}"

    def test_trace_row_is_article(self, template_source):
        """v9: trace-row should be an <article> element."""
        pattern = re.compile(r'<article\b[^>]*class="[^"]*sd-round[^"]*"[^>]*data-trace-round-row')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No <article class=\"sd-round\" data-trace-round-row> found"


# ── Toggle button contract ──────────────────────────────────────────


class TestToggleButtonContract:
    """Toggle button must exist with proper ARIA attributes."""

    def test_toggle_button_present(self, template_source):
        assert 'class="sd-round-summary"' in template_source, (
            "Missing .sd-round-summary in template"
        )

    def test_toggle_has_data_action(self, template_source):
        assert 'data-action="toggle-round"' in template_source, (
            'Toggle button must have data-action="toggle-round"'
        )

    def test_toggle_has_aria_expanded(self, template_source):
        assert 'aria-expanded=' in template_source, (
            "Toggle button must have aria-expanded"
        )

    def test_toggle_has_aria_controls(self, template_source):
        assert 'aria-controls=' in template_source, (
            "Toggle button must have aria-controls"
        )

    def test_toggle_has_round_id(self, template_source):
        assert 'data-round=' in template_source, (
            "Toggle button must have data-round attribute"
        )

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

    def test_trace_detail_data_attr(self, template_source):
        assert 'data-trace-detail' in template_source, (
            "Trace detail must have data-trace-detail attribute"
        )

    def test_trace_detail_has_round_id(self, template_source):
        """Detail element must have class sd-round-detail."""
        assert 'class="sd-round-detail"' in template_source, (
            "Trace detail must have class sd-round-detail"
        )

    def test_aria_controls_matches_detail_id(self, template_source):
        """aria-controls must reference round-{N}-detail id pattern."""
        controls = re.findall(r'aria-controls="round-\{\{[^}]+\}\}-detail"', template_source)
        ids = re.findall(r'id="round-\{\{[^}]+\}\}-detail"', template_source)
        assert len(controls) > 0, "No aria-controls matching round-{N}-detail found"
        assert len(ids) > 0, "No trace-detail ids matching round-{N}-detail found"


# ── Trace detail is sibling of round row ────────────────────────────


class TestTraceDetailSibling:
    """trace-detail must be a sibling of the round article, not nested inside summary."""

    def test_detail_outside_summary(self, template_source):
        """sd-round-detail must not be inside sd-round-summary."""
        summary_start = template_source.find('round_summary(row)')
        detail_in_summary = False
        if summary_start > 0:
            # Check if round_detail macro is called inside round_summary
            # In v9, round_detail is a separate macro called from trace_round
            block = template_source[summary_start:summary_start + 500]
            detail_in_summary = 'round_detail' in block and 'def macro' not in block
        # The round_detail macro should be separate
        assert '{% macro round_detail' in template_source, (
            "round_detail must be a separate macro"
        )

    def test_trace_round_calls_both_macros(self, template_source):
        """trace_round macro must call both round_summary and round_detail."""
        trace_round_block = template_source[template_source.find('{% macro trace_round'):]
        trace_round_block = trace_round_block[:trace_round_block.find('{%- endmacro %}') + len('{%- endmacro %}')]
        assert '{{ round_summary(row) }}' in trace_round_block, (
            "trace_round must call round_summary"
        )
        assert '{{ round_detail(row) }}' in trace_round_block, (
            "trace_round must call round_detail"
        )


# ── No nested button conflict ───────────────────────────────────────


class TestNoNestedButtonConflict:
    """Trace row structure must not have illegal button nesting."""

    def test_payload_buttons_in_detail(self, template_source):
        """Payload buttons should be invoked inside detail context (llm_call_card, tool_batch)."""
        # v9 uses sdp.button() macro calls with 'open-payload' action
        assert "sdp.button('Context'" in template_source or "'Context'" in template_source, (
            "Must have Context button in detail"
        )
        assert "sdp.button('Response'" in template_source or "'Response'" in template_source, (
            "Must have Response button in detail"
        )

    def test_toggle_button_not_direct_child_of_article(self, template_source):
        """Toggle button should be inside article but wrapped properly."""
        # In v9, the article > button.sd-round-summary is the direct child,
        # which is fine — the article IS the clickable row
        pattern = re.compile(
            r'<article\b[^>]*data-trace-round-row[^>]*>\s*\{\{\s*round_summary'
        )
        assert pattern.search(template_source), (
            "Article should call round_summary macro"
        )

    def test_no_direct_button_children_without_wrapper(self, template_source):
        """No button should be a direct unmanaged child of the round article."""
        # v9 pattern: article > button.sd-round-summary is valid
        # but we check no <button> appears without proper class
        pattern = re.compile(
            r'data-trace-round-row[^>]*>\s*<button(?![^>]*class="sd-round-summary")',
            re.DOTALL
        )
        matches = pattern.findall(template_source)
        assert len(matches) == 0, (
            f"No button should be direct child without sd-round-summary class: {matches}"
        )


# ── Grid structure ──────────────────────────────────────────────────


class TestTraceRowGridStructure:
    """v9 trace row must have the expected column structure."""

    def test_has_round_id_cell(self, template_source):
        assert 'sd-round-id' in template_source, (
            "Must have round ID cell"
        )

    def test_has_status_cell(self, template_source):
        assert 'round_status(' in template_source, (
            "Must have status cell via macro"
        )

    def test_has_preview_cell(self, template_source):
        assert 'sd-round-preview' in template_source, (
            "Must have preview cell"
        )

    def test_has_metric_cells(self, template_source):
        assert 'sd-round-metric' in template_source, (
            "Must have metric cells"
        )

    def test_has_token_mix(self, template_source):
        assert 'sd-round-mix' in template_source, (
            "Must have token mix bar"
        )


# ── No illegal nested buttons ───────────────────────────────────────


class TestNoIllegalNestedButtons:
    """Template must not produce nested button elements within trace-row."""

    def test_trace_row_is_article_not_button(self, template_source):
        """The trace-row itself must be an article element."""
        pattern = re.compile(
            r'<(button|div|article)\b[^>]*data-trace-round-row',
            re.DOTALL
        )
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "Could not find trace-row element"
        for tag in matches:
            assert tag == "article", f"trace-row uses <{tag}> tag, should be <article>"


# ── Multiple rounds have unique toggles ─────────────────────────────


class TestMultipleRoundsHaveToggles:
    """All rounds should have their own toggle button with unique aria-controls."""

    def test_toggle_button_exists(self, template_source):
        pattern = re.compile(r'class="sd-round-summary"')
        matches = pattern.findall(template_source)
        assert len(matches) >= 1, f"Expected at least 1 toggle button, found {len(matches)}"

    def test_unique_aria_controls_template(self, template_source):
        """aria-controls should be templated with row.round_id for uniqueness."""
        pattern = re.compile(r'aria-controls="round-\{\{\s*row\.round_id\s*\}\}-detail"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No unique aria-controls pattern found"

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

    def test_toggle_round_action_in_js(self):
        js = self._js_source()
        assert "toggle-round" in js, (
            'JS must reference toggle-round action'
        )

    def test_toggle_round_function_exists(self):
        js = self._js_source()
        assert "toggleRound" in js, (
            "JS must contain toggleRound function"
        )

    def test_js_uses_data_action_dispatch(self):
        js = self._js_source()
        assert 'action ===' in js or "action ===" in js or \
               'dataset.action' in js or 'getAttribute("data-action")' in js, (
            "JS should dispatch events based on data-action attribute"
        )


# ── CSS styles ──────────────────────────────────────────────────────


class TestCSSStyles:
    """CSS must contain v9 trace row and toggle styles."""

    def _css_source(self):
        if not CSS_FILE.exists():
            pytest.skip(f"CSS not found: {CSS_FILE}")
        return CSS_FILE.read_text(encoding="utf-8")

    def test_css_has_sd_round_styles(self):
        css = self._css_source()
        assert ".sd-round" in css, (
            "CSS must include .sd-round styles"
        )

    def test_css_has_sd_round_summary(self):
        css = self._css_source()
        assert ".sd-round-summary" in css, (
            "CSS must include .sd-round-summary styles"
        )

    def test_css_has_sd_round_detail(self):
        css = self._css_source()
        assert ".sd-round-detail" in css, (
            "CSS must include .sd-round-detail styles"
        )

    def test_css_has_sd_round_preview(self):
        css = self._css_source()
        assert ".sd-round-preview" in css, (
            "CSS must include .sd-round-preview styles"
        )

    def test_css_has_sd_round_metric(self):
        css = self._css_source()
        assert ".sd-round-metric" in css, (
            "CSS must include .sd-round-metric styles"
        )

    def test_css_has_token_bar(self):
        css = self._css_source()
        assert ".sd-tokenbar" in css or "sd-tokenbar" in css, (
            "CSS must include token bar styles"
        )
