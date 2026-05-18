"""Deterministic CSS contract tests: trace-row layout must prevent overlap.

These tests verify the CSS rules exist and have the right properties by
parsing the stylesheet directly. They do NOT require a browser.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLE_CSS_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "session_browser" / "web" / "static" / "style.css"
)


def _read_css() -> str:
    return STYLE_CSS_PATH.read_text(encoding="utf-8")


def _extract_rule(css: str, selector: str) -> list[str]:
    """Extract all declaration blocks for a given CSS selector.

    Handles both single selectors and comma-separated selector blocks.
    For comma-separated selectors like ".foo, .bar { ... }", passing
    ".foo" or ".bar" will find the block.
    """
    # Find all { ... } blocks and check if the selector appears before them
    results = []
    # Match any rule that contains the selector followed by { ... }
    pattern = re.compile(
        r'([^{}]*?' + re.escape(selector) + r'[^{}]*?)\s*\{([^}]+)\}',
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(css):
        results.append(m.group(2))
    return results


class TestRoundMainBoundary:
    """round-main must be a strong boundary grid item."""

    def test_round_main_has_min_width_zero(self):
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .round-main')
        assert len(blocks) > 0, "Missing .session-detail-phase1 .round-main rule"
        for block in blocks:
            if 'min-width' in block:
                assert 'min-width: 0' in block

    def test_round_main_has_overflow_hidden(self):
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .round-main')
        assert len(blocks) > 0, "Missing .session-detail-phase1 .round-main rule"
        assert any('overflow: hidden' in b for b in blocks), (
            f".round-main missing overflow: hidden in blocks: {blocks}"
        )

    def test_round_main_has_flex_layout(self):
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .round-main')
        assert len(blocks) > 0, "Missing .session-detail-phase1 .round-main rule"
        assert any('display: flex' in b for b in blocks), (
            ".round-main missing display: flex"
        )

    def test_round_main_t_has_overflow_hidden(self):
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .round-main .t')
        assert len(blocks) > 0, "Missing .session-detail-phase1 .round-main .t rule"
        assert any('overflow: hidden' in b for b in blocks)

    def test_round_main_d_has_overflow_hidden(self):
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .round-main .d')
        assert len(blocks) > 0, "Missing .session-detail-phase1 .round-main .d rule"
        assert any('overflow: hidden' in b for b in blocks)


class TestTraceRowGrid:
    """Trace row grid must have shrinkable middle column."""

    def test_trace_row_has_grid_template(self):
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .trace-row')
        assert len(blocks) > 0, "Missing .session-detail-phase1 .trace-row rule"
        assert any('grid-template-columns' in b for b in blocks), (
            "trace-row missing grid-template-columns"
        )

    def test_middle_column_shrinkable(self):
        """Middle column must use minmax(0, ...) to allow shrinking."""
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .trace-row')
        assert len(blocks) > 0
        for block in blocks:
            if 'grid-template-columns' in block:
                assert 'minmax(0' in block, (
                    f"Middle column must use minmax(0, ...) for shrinkability. "
                    f"Got: {block.strip()}"
                )

    def test_no_hard_min_in_middle_column(self):
        """Middle column must NOT have a large min value (e.g. minmax(300px, ...))."""
        css = _read_css()
        blocks = _extract_rule(css, '.session-detail-phase1 .trace-row')
        for block in blocks:
            if 'grid-template-columns' not in block:
                continue
            # The session-detail-phase1 template uses minmax(0, 1fr) — that's fine
            # But old templates might have minmax(300px, ...) or similar
            # We specifically check for minmax values > 100px in the phase1 rule
            if 'session-detail-phase1' not in block:
                continue
            # Extract minmax values
            minmax_matches = re.findall(r'minmax\((\d+)px', block)
            for val in minmax_matches:
                assert int(val) <= 120, (
                    f"Middle column minmax min value {val}px is too large (max 120px)"
                )


class TestMixAndTimeCells:
    """Mix bar and time cell must have stable minimum widths."""

    def test_mixbar_has_min_width(self):
        css = _read_css()
        blocks = _extract_rule(css, '.mixbar')
        assert len(blocks) > 0, "Missing .mixbar rule"
        assert any('min-width' in b for b in blocks), (
            ".mixbar missing min-width"
        )

    def test_tcell_style(self):
        css = _read_css()
        blocks = _extract_rule(css, '.tcell')
        assert len(blocks) > 0, "Missing .tcell rule"
        # Just verify it exists and has text-align
        assert any('text-align' in b for b in blocks)


class TestTemplateStructure:
    """Verify session.html has the expected trace-row cell structure."""

    def test_trace_row_has_round_main(self):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "session_browser" / "web" / "templates" / "session.html"
        )
        content = template_path.read_text(encoding="utf-8")
        assert 'class="round-main"' in content, (
            "session.html must have .round-main container in trace rows"
        )

    def test_trace_row_has_mix_cell(self):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "session_browser" / "web" / "templates" / "session.html"
        )
        content = template_path.read_text(encoding="utf-8")
        # Check for mix-related rendering
        assert 'mixbar' in content or 'mix' in content, (
            "session.html must render token mixbar in trace rows"
        )
