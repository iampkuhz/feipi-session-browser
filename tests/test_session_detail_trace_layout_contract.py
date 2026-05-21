"""Deterministic CSS contract tests: trace-table layout must prevent overlap.

v18: Table-based layout uses .trace-table, .round-row, .expanded-row.
Tests verify CSS rules exist in css/session-detail.css.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "session_browser" / "web" / "static" / "css" / "session-detail.css"
)


def _read_css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


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


class TestRoundRowLayout:
    """v18: .round-row must have proper layout."""

    def test_round_row_has_layout(self):
        css = _read_css()
        blocks = _extract_rule(css, '.round-row')
        assert len(blocks) > 0, "Missing .round-row rule in CSS"

    def test_expanded_row_hidden(self):
        css = _read_css()
        blocks = _extract_rule(css, '.expanded-row')
        assert len(blocks) > 0, "Missing .expanded-row rule"
        assert any('none' in b for b in blocks), (
            ".expanded-row must have display: none by default"
        )

    def test_round_row_is_open_shows_expanded(self):
        css = _read_css()
        # Check for selector that shows expanded row when round is open
        assert '.round-row.is-open + .expanded-row' in css or 'is-open' in css, (
            "CSS must show expanded-row when round-row is-open"
        )


class TestTraceTable:
    """v18 trace table must have proper structure."""

    def test_trace_table_has_layout(self):
        css = _read_css()
        blocks = _extract_rule(css, '.trace-table')
        assert len(blocks) > 0, "Missing .trace-table rule"
        assert any('border-collapse' in b or 'table-layout' in b for b in blocks), (
            ".trace-table must have table layout properties"
        )


class TestMixAndTimeCells:
    """v18: token bar and metrics must have stable styles."""

    def test_tokenbar_has_min_width(self):
        css = _read_css()
        blocks = _extract_rule(css, '.tokenbar')
        assert len(blocks) > 0, "Missing .tokenbar rule"

    def test_sd_round_metric_style(self):
        css = _read_css()
        blocks = _extract_rule(css, '.sd-round-metric')
        assert len(blocks) > 0, "Missing .sd-round-metric rule"


class TestTemplateStructure:
    """Verify session.html has the expected v18 trace structure via component macros."""

    def test_trace_row_has_trace_round(self):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "session_browser" / "web" / "templates" / "session.html"
        )
        content = template_path.read_text(encoding="utf-8")
        # v18 uses sdt.trace_round macro which renders <tr> rows
        assert 'sdt.trace_round' in content, (
            "session.html must call sdt.trace_round macro"
        )

    def test_trace_table_structure(self):
        template_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "session_browser" / "web" / "templates" / "session.html"
        )
        content = template_path.read_text(encoding="utf-8")
        # v18 uses <table class="trace-table">
        assert 'class="trace-table"' in content, (
            "session.html must have <table class=\"trace-table\">"
        )

    def test_trace_row_has_token_mix(self):
        css = _read_css()
        # v18 uses tokenbar in metric-stack
        assert 'tokenbar' in css or 'sd-tokenbar' in css, (
            "CSS must include token bar styles"
        )
