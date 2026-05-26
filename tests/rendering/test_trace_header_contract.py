"""Trace header contract test (T021 / SD-15).

Verifies that the session detail trace_header macro:
- Does NOT contain the sd-trace-title class
- Does NOT contain data-action="collapse-all"
- DOES contain data-action="toggle-all" (or toggle-all class)

This contract ensures the trace header only needs a toggle-all button
without a separate sd-trace-title or collapse-all element.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TIMELINE_HTML = ROOT / "src" / "session_browser" / "web" / "templates" / "components" / "session_detail_timeline.html"


@pytest.fixture(scope="module")
def trace_header_source():
    """Extract the trace_header macro body from the template."""
    if not TIMELINE_HTML.exists():
        pytest.skip(f"Template not found at {TIMELINE_HTML}")
    text = TIMELINE_HTML.read_text(encoding="utf-8")
    # Locate the trace_header macro block
    start = text.find("{% macro trace_header()")
    if start == -1:
        pytest.fail("trace_header macro not found in session_detail_timeline.html")
    end = text.find("{%- endmacro %}", start)
    if end == -1:
        pytest.fail("trace_header macro lacks closing endmacro")
    # Include the endmacro marker
    return text[start:end + len("{%- endmacro %}")]


class TestTraceHeaderContract:
    """trace_header must NOT contain sd-trace-title or collapse-all,
    and MUST contain toggle-all.
    """

    def test_no_sd_trace_title(self, trace_header_source):
        """trace_header must not contain sd-trace-title class."""
        assert "sd-trace-title" not in trace_header_source, (
            "trace_header must NOT contain sd-trace-title class"
        )

    def test_no_collapse_all_action(self, trace_header_source):
        """trace_header must not contain data-action=\"collapse-all\"."""
        assert 'data-action="collapse-all"' not in trace_header_source, (
            "trace_header must NOT contain data-action=\"collapse-all\""
        )

    def test_no_collapse_all_class(self, trace_header_source):
        """trace_header must not contain sd-collapse-all-btn class."""
        assert "sd-collapse-all-btn" not in trace_header_source, (
            "trace_header must NOT contain sd-collapse-all-btn class"
        )

    def test_has_toggle_all(self, trace_header_source):
        """trace_header must contain data-action=\"toggle-all\" or toggle-all class."""
        has_action = 'data-action="toggle-all"' in trace_header_source
        has_class = "toggle-all" in trace_header_source
        assert has_action or has_class, (
            "trace_header must contain data-action=\"toggle-all\" or toggle-all class"
        )
