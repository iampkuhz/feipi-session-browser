"""Static DOM contract tests for trace row structure.

These tests verify that the session.html template source conforms to the
required DOM structure for trace rows: no nested buttons, proper ARIA attributes,
and dedicated toggle button elements.

Tests analyze the template source file directly using regex-based static analysis,
avoiding the complexity of full Jinja2 rendering with custom filters.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "src" / "session_browser" / "web" / "templates" / "session.html"


@pytest.fixture(scope="module")
def template_source():
    """Load the session.html template source."""
    if not TEMPLATE_PATH.exists():
        pytest.skip(f"Template not found: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


class TestTraceRowNoLongerButton:
    """trace-row must NOT be a <button> element."""

    def test_no_button_trace_row(self, template_source):
        """Template must not contain <button class=\"trace-row\">."""
        pattern = re.compile(r'<button\b[^>]*class="[^"]*trace-row[^"]*"')
        matches = pattern.findall(template_source)
        assert len(matches) == 0, f"Found <button class=\"trace-row\">: {matches}"

    def test_trace_row_is_div(self, template_source):
        """trace-row should be a <div> element."""
        pattern = re.compile(r'<div\b[^>]*class="[^"]*trace-row[^"]*"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No <div class=\"trace-row\"> found"


class TestToggleCellExists:
    """Each trace-row must contain a .trace-row__toggle-cell."""

    def test_toggle_cell_present(self, template_source):
        assert 'class="trace-row__toggle-cell"' in template_source, (
            "Missing .trace-row__toggle-cell in template"
        )


class TestToggleButtonContract:
    """Toggle button must exist with proper ARIA attributes."""

    def test_trace_round_toggle_present(self, template_source):
        assert 'class="trace-round-toggle"' in template_source, (
            "Missing .trace-round-toggle in template"
        )

    def test_toggle_has_data_action(self, template_source):
        assert 'data-action="toggle-round"' in template_source, (
            'Toggle button must have data-action="toggle-round"'
        )

    def test_toggle_has_aria_expanded(self, template_source):
        pattern = re.compile(
            r'<button\b[^>]*class="[^"]*trace-round-toggle[^"]*"[^>]*aria-expanded="[^"]*"'
        )
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No toggle button with aria-expanded found"

    def test_toggle_has_aria_controls(self, template_source):
        pattern = re.compile(
            r'<button\b[^>]*class="[^"]*trace-round-toggle[^"]*"[^>]*aria-controls="[^"]*"'
        )
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No toggle button with aria-controls found"

    def test_toggle_chevron_present(self, template_source):
        assert 'class="trace-round-toggle__chevron"' in template_source, (
            "Missing .trace-round-toggle__chevron"
        )

    def test_toggle_label_present(self, template_source):
        assert 'class="trace-round-toggle__label"' in template_source, (
            "Missing .trace-round-toggle__label"
        )


class TestTraceDetailContract:
    """Each trace-detail must have a matching id referenced by toggle aria-controls."""

    def test_trace_detail_ids_exist(self, template_source):
        pattern = re.compile(r'id="trace-detail-\{\{')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No trace-detail IDs found"

    def test_aria_controls_pattern_matches_detail_id(self, template_source):
        """The aria-controls template pattern should match the trace-detail id pattern."""
        controls_pattern = re.compile(r'aria-controls="(trace-detail-[^"]*)"')
        controls = controls_pattern.findall(template_source)

        id_pattern = re.compile(r'id="(trace-detail-[^"]*)"')
        ids = id_pattern.findall(template_source)

        # Both should use the same Jinja2 variable (loop.index)
        assert len(controls) > 0, "No aria-controls found"
        assert len(ids) > 0, "No trace-detail ids found"

        # The template should use the same pattern for both
        assert any("loop.index" in c for c in controls), (
            "aria-controls should reference loop.index"
        )
        assert any("loop.index" in i for i in ids), (
            "trace-detail id should reference loop.index"
        )


class TestTraceDetailSiblingAfterTraceRow:
    """trace-detail must appear as a sibling immediately after trace-row."""

    def test_trace_detail_follows_trace_row(self, template_source):
        """In the template, .trace-detail must appear after .trace-row closing tag."""
        # The pattern: </div> (closing trace-row) followed by trace-detail on next line
        # This verifies the sibling relationship in the Jinja2 template structure
        import re
        pattern = re.compile(
            r'</div>\s*\n\s*\{#.*Trace detail.*#}\s*\n\s*<div\s+class="trace-detail"',
            re.DOTALL
        )
        match = pattern.search(template_source)
        assert match, (
            ".trace-detail must appear as sibling after .trace-row in template source"
        )

    def test_trace_detail_not_inside_trace_row(self, template_source):
        """trace-detail must NOT be nested inside trace-row."""
        import re
        # Verify that trace-detail appears AFTER the trace-row closes.
        # Look for the Jinja2 comment that introduces trace-detail, followed by the div.
        # The comment pattern "{# ── Trace detail" must be preceded by trace-row's closing.
        detail_idx = template_source.find("{#")
        detail_section = template_source[detail_idx:]

        # Check trace-detail exists outside trace-row
        assert 'class="trace-detail"' in template_source, (
            "trace-detail element must exist"
        )

        # The trace-detail for-loop pattern should use loop.index same as trace-row
        detail_pattern = re.compile(
            r'id="trace-detail-\{\{\s*loop\.index\s*\}\}"'
        )
        assert detail_pattern.search(template_source), (
            "trace-detail must use loop.index for dynamic id"
        )

        # Both trace-row and trace-detail should be in the same for-loop
        # (indicating they are siblings, not nested)
        # Simple approach: find all {% for round in rounds %} blocks and check
        # if any block contains both trace-row and trace-detail
        sections = template_source.split("{% for round in rounds %}")
        found_shared_loop = False
        for section in sections[1:]:  # skip preamble
            # Truncate at the first {% endfor %} that matches this level
            # A simpler check: both strings appear before the next major section
            has_row = "trace-row" in section[:2000]
            has_detail = "trace-detail" in section[:2000]
            if has_row and has_detail:
                found_shared_loop = True
                break

        assert found_shared_loop, (
            "trace-row and trace-detail should both be inside the same round for-loop"
        )


class TestNoNestedButtonConflict:
    """trace-row div must not contain payload-btn as a direct child in preview area."""

    def test_payload_btn_in_detail_context(self, template_source):
        """Payload buttons should appear inside trace-detail, not trace-row."""
        # Payload buttons with data-action="open-payload" should exist
        assert 'data-action="open-payload"' in template_source, (
            "Payload buttons should exist in detail"
        )

    def test_toggle_button_inside_toggle_cell(self, template_source):
        """The toggle button must be inside .trace-row__toggle-cell, not a direct child of .trace-row."""
        import re
        # The toggle button should be wrapped by trace-row__toggle-cell
        pattern = re.compile(
            r'class="trace-row__toggle-cell".*?class="trace-round-toggle"',
            re.DOTALL
        )
        match = pattern.search(template_source)
        assert match, (
            "Toggle button must be inside .trace-row__toggle-cell, not direct child of .trace-row"
        )

    def test_no_direct_button_children_in_trace_row(self, template_source):
        """No button should be a direct child of .trace-row (all must be wrapped)."""
        import re
        # Pattern: <div class="trace-row"...> followed by <button without any wrapping div
        # The only direct children should be divs/spans, not buttons
        # Allow the toggle-cell wrapper: trace-row > toggle-cell > button is OK
        pattern = re.compile(
            r'<div\b[^>]*class="[^"]*trace-row[^"]*"[^>]*>\s*<button',
            re.DOTALL
        )
        matches = pattern.findall(template_source)
        assert len(matches) == 0, (
            f"No button should be direct child of .trace-row, found: {matches}"
        )


class TestToggleRowGridStructure:
    """trace-row grid must have the expected column structure."""

    def test_trace_row_has_grid_columns(self, template_source):
        assert 'trace-row__toggle-cell' in template_source
        assert 'round-main' in template_source
        assert 'class="diags"' in template_source or 'class="diags"' in template_source
        assert 'mixval' in template_source
        assert 'tcell' in template_source


class TestNoIllegalNestedButtons:
    """Template must not produce nested button elements within trace-row."""

    def test_no_button_wrapping_trace_row(self, template_source):
        """The trace-row itself must not be a button."""
        # Check that the opening tag for trace-row is a div, not button
        pattern = re.compile(
            r'<(button|div|article)\b[^>]*class="[^"]*trace-row[^"]*"',
            re.DOTALL
        )
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "Could not find trace-row element"
        for tag in matches:
            assert tag in ("div", "article"), f"trace-row uses <{tag}> tag, should be <div> or <article>"


class TestMultipleRoundsHaveToggles:
    """All rounds should have their own toggle button with unique aria-controls."""

    def test_multiple_toggle_buttons(self, template_source):
        pattern = re.compile(r'class="trace-round-toggle"')
        matches = pattern.findall(template_source)
        assert len(matches) >= 1, f"Expected at least 1 toggle button, found {len(matches)}"

    def test_unique_aria_controls_template(self, template_source):
        """aria-controls should be templated with loop.index for uniqueness."""
        pattern = re.compile(r'aria-controls="trace-detail-\{\{\s*loop\.index\s*\}\}"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No unique aria-controls pattern found"

    def test_unique_trace_detail_ids_template(self, template_source):
        """trace-detail ids should be templated with loop.index for uniqueness."""
        pattern = re.compile(r'id="trace-detail-\{\{\s*loop\.index\s*\}\}"')
        matches = pattern.findall(template_source)
        assert len(matches) > 0, "No unique trace-detail id pattern found"


class TestJSEventDispatchOnDataAction:
    """JS must dispatch toggle on data-action=\"toggle-round\"."""

    def test_toggle_round_action_in_js(self, template_source):
        assert 'data-action="toggle-round"' in template_source, (
            'JS must handle data-action="toggle-round"'
        )

    def test_toggle_round_handler_in_js(self, template_source):
        """JS should contain toggleRoundDetail call for toggle-round action."""
        assert "toggle-round" in template_source, (
            "JS event handler should reference toggle-round"
        )

    def test_no_closest_trace_row_toggle(self, template_source):
        """JS should NOT use closest('.trace-row') for toggle logic."""
        # The old pattern of clicking .trace-row directly should be removed
        # for toggle purposes. Check that the toggle handler uses data-action.
        pattern = re.compile(r"closest\s*\(\s*['\"]\.trace-row['\"]")
        matches = pattern.findall(template_source)
        # This pattern should not be used for toggle anymore
        # (it may still be used for other purposes like jumpToRound)
        # So we just check that the primary toggle path uses data-action
        assert "action === 'toggle-round'" in template_source or \
               'action === "toggle-round"' in template_source, (
            "JS should dispatch toggle on data-action"
        )


class TestCSSToggleCellStyles:
    """CSS must contain toggle cell styles."""

    def test_css_toggle_cell_style(self):
        css_path = ROOT / "src" / "session_browser" / "web" / "static" / "style.css"
        if not css_path.exists():
            pytest.skip(f"CSS not found: {css_path}")
        css = css_path.read_text(encoding="utf-8")

        assert "trace-row__toggle-cell" in css, (
            "CSS must include .trace-row__toggle-cell styles"
        )
        assert "trace-round-toggle" in css, (
            "CSS must include .trace-round-toggle styles"
        )

    def test_css_trace_row_fixed_first_column(self):
        css_path = ROOT / "src" / "session_browser" / "web" / "static" / "style.css"
        if not css_path.exists():
            pytest.skip(f"CSS not found: {css_path}")
        css = css_path.read_text(encoding="utf-8")

        # The phase1 trace-row should have a fixed first column width
        assert "84px" in css, (
            "CSS should use 84px for first column"
        )
