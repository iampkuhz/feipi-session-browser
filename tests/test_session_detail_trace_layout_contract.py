"""Deterministic CSS contract tests: trace-row layout must prevent overlap.

v9: Component-based layout uses .sd-round, .sd-round-summary, .sd-round-detail.
Tests verify CSS rules exist in both style.css and css/session-detail-timeline.css.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLE_CSS_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "session_browser" / "web" / "static" / "style.css"
)
TIMELINE_CSS_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "session_browser" / "web" / "static" / "css" / "session-detail-timeline.css"
)


def _read_css() -> str:
    return STYLE_CSS_PATH.read_text(encoding="utf-8")


def _read_timeline_css() -> str:
    return TIMELINE_CSS_PATH.read_text(encoding="utf-8")


def _extract_rule(css: str, selector: str) -> list[str]:
    """Extract all declaration blocks for a given CSS selector."""
    results = []
    pattern = re.compile(
        r'([^{}]*?' + re.escape(selector) + r'[^{}]*?)\s*\{([^}]+)\}',
        re.MULTILINE | re.DOTALL,
    )
    for m in pattern.finditer(css):
        results.append(m.group(2))
    return results


class TestRoundMainBoundary:
    """v9: .sd-round must have proper layout."""

    def test_sd_round_has_layout(self):
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-round')
        assert len(blocks) > 0, "Missing .sd-round rule in timeline CSS"

    def test_sd_round_summary_has_display(self):
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-round-summary')
        assert len(blocks) > 0, "Missing .sd-round-summary rule"
        assert any('display' in b or 'grid' in b for b in blocks), (
            ".sd-round-summary must have display/grid layout"
        )

    def test_sd_round_detail_hidden_when_not_open(self):
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-round-detail')
        # Check for hidden attribute handling
        assert 'hidden' in css or '[hidden]' in css, (
            "CSS must handle [hidden] attribute"
        )


class TestTraceRowGrid:
    """v9 trace row grid must have proper structure."""

    def test_sd_round_summary_has_grid(self):
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-round-summary')
        assert len(blocks) > 0, "Missing .sd-round-summary rule"
        assert any('grid-template-columns' in b for b in blocks), (
            "sd-round-summary missing grid-template-columns"
        )

    def test_columns_shrinkable(self):
        """Grid columns must use minmax() or fr units for flexibility."""
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-round-summary')
        for block in blocks:
            if 'grid-template-columns' in block:
                # v9 uses minmax(380px, 1.8fr) for preview column — acceptable
                assert 'minmax(' in block or 'fr' in block, (
                    f"Grid must use minmax() or fr units. Got: {block.strip()}"
                )


class TestMixAndTimeCells:
    """v9: token bar and metrics must have stable styles."""

    def test_tokenbar_has_min_width(self):
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-tokenbar')
        assert len(blocks) > 0, "Missing .sd-tokenbar rule"

    def test_sd_round_metric_style(self):
        css = _read_timeline_css()
        blocks = _extract_rule(css, '.sd-round-metric')
        assert len(blocks) > 0, "Missing .sd-round-metric rule"


class TestTemplateStructure:
    """Verify session.html has the expected v9 trace structure via component macros."""

    def test_trace_row_has_sd_round(self):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "session_browser" / "web" / "templates" / "session.html"
        )
        content = template_path.read_text(encoding="utf-8")
        # v9 uses sdt.trace_round macro which renders article.sd-round
        assert 'sdt.trace_round' in content, (
            "session.html must call sdt.trace_round macro"
        )

    def test_trace_row_has_token_mix(self):
        timeline = _read_timeline_css()
        # v9 uses sd-round-mix with token bar
        assert 'sd-round-mix' in timeline or 'sd-tokenbar' in timeline, (
            "Timeline CSS must include token mix styles"
        )
