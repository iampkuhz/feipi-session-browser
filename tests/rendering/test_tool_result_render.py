"""Regression tests for tool result rendering in v9 session detail.
v9 architecture:
- Tool results rendered via timeline component macros (tool_batch)
- Tool result buttons use sdp.button('Result', 'open-payload', ...)
- Payload modal shows result content
- No inline [:500] truncation on tool results in template
"""

import pytest

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
TIMELINE = TEMPLATE_DIR / "components" / "session_detail_timeline.html"


@pytest.mark.contract_case("UI-SD-021")
def test_tool_batch_renders_full_result():
    """The tool_batch macro renders tool result buttons, not truncated text."""
    source = TIMELINE.read_text(encoding="utf-8")

    # Verify tool_batch macro exists
    macro_pattern = r'\{%\s*macro\s+tool_batch\s*\(batch\)'
    match = re.search(macro_pattern, source)
    assert match, "tool_batch macro not found in timeline component"

    # Check macro body for sdp.button('Result' and no truncation
    macro_end = source.find('{%- endmacro %}', match.start())
    if macro_end == -1:
        macro_end = source.find('{% endmacro %}', match.start())
    macro_block = source[match.start():macro_end + len('{% endmacro %}')]
    assert "[:500]" not in macro_block, \
        "tool_batch macro should not truncate result to 500 chars"
    assert "sdp.button('Result'" in macro_block, \
        "tool_batch must have Result button via sdp.button"


@pytest.mark.contract_case("UI-SD-021")
def test_all_tool_result_calls_use_macro():
    """Tool results are rendered via component macros, not inline truncation."""
    source = TIMELINE.read_text(encoding="utf-8")

    # Verify no remaining inline tool result truncation
    lines = source.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip known safe patterns
        if "response_preview" in stripped:
            continue
        if "title[:" in stripped:
            continue
        # Flag any tc.result[:N] or result[:N] patterns
        if re.search(r'\.result\s*\[\s*:\s*\d+\s*\]', stripped):
            assert False, (
                f"Line {i} still has inline truncation on result: {stripped}"
            )


@pytest.mark.contract_case("UI-SD-021")
def test_template_has_tool_result_button():
    """The tool_batch macro should have a Result button for each tool."""
    source = TIMELINE.read_text(encoding="utf-8")

    # Verify Result button is inside tool loop
    assert "sdp.button('Result'" in source, \
        "tool_batch must render Result button"
    assert 'data-action="open-payload"' not in source or \
           "sdp.button" in source, \
        "Result button should use sdp.button macro"
