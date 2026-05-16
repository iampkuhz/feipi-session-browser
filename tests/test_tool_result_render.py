"""Regression tests for tool result rendering in session.html template.

Ensures that:
- Tool results are NOT truncated to 500 chars.
- The render_tool_result macro produces the expected HTML structure.
- The template source does not contain [:500] truncation on tool results.
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"


def test_render_tool_result_macro_produces_full_result():
    """The render_tool_result macro renders full result, not truncated."""
    template_file = TEMPLATE_DIR / "session.html"
    source = template_file.read_text(encoding="utf-8")

    # Verify the macro definition exists and does NOT use [:500] slicing
    macro_pattern = r'\{%\s*macro\s+render_tool_result\(result\)\s*%\}.*?\{%\s*endmacro\s*%\}'
    match = re.search(macro_pattern, source, re.DOTALL)
    assert match, "render_tool_result macro not found in session.html"

    macro_body = match.group()
    assert "[:500]" not in macro_body, \
        "render_tool_result macro should not truncate result to 500 chars"
    assert re.search(r'\{\{\s*result\s*(\|.*?)?\s*\}\}', macro_body), \
        "Macro should output the full result without slicing"
    assert "tool-result-block" in macro_body
    assert "tool-result-wrapper" in macro_body
    assert "tool-result-raw" in macro_body
    assert "tool-result-md" in macro_body


def test_all_tool_result_calls_use_macro():
    """Tool result macro is defined; timeline detail uses timeline_node macro."""
    template_file = TEMPLATE_DIR / "session.html"
    source = template_file.read_text(encoding="utf-8")

    # After Timeline tab refactoring, round detail uses timeline_node macro
    # instead of inline render_tool_result calls. Verify the macro is still
    # defined and no inline tc.result[:N] truncation remains.
    macro_def = re.search(r'\{%\s*macro\s+render_tool_result\(result\)\s*%\}', source)
    assert macro_def, "render_tool_result macro should still be defined"

    # Verify no remaining inline tool result truncation
    lines = source.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip the macro definition itself and Profile tab's response preview
        if "macro render_tool_result" in stripped:
            continue
        if "response_full[:500]" in stripped:
            continue
        if "response_preview[:80]" in stripped:
            continue
        if "title[:" in stripped:
            continue
        # Flag any remaining tc.result[:N] patterns
        if re.search(r'tc\.result\s*\[\s*:\s*\d+\s*\]', stripped):
            assert False, (
                f"Line {i} still has inline truncation on tc.result: {stripped}"
            )


def test_template_has_tool_result_block_structure():
    """The macro should wrap result in tool-result-block for JS DOM traversal."""
    template_file = TEMPLATE_DIR / "session.html"
    source = template_file.read_text(encoding="utf-8")

    # Verify the JS toggle function uses closest('.tool-result-block')
    assert "closest('.tool-result-block')" in source, \
        "toggleResultMd JS should use closest('.tool-result-block')"
    assert "closest('.tool-result-wrapper')" not in source, \
        "toggleResultMd JS should NOT use closest('.tool-result-wrapper')"
