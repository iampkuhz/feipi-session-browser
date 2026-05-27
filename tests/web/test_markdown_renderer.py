"""Tests for session_browser.web.renderers.markdown module.

Covers:
- Basic markdown to HTML conversion (headings, lists, emphasis)
- Code block rendering
- Table rendering
- XSS protection (HTML escaping)
- Empty/None input handling
- Special character handling
"""
from __future__ import annotations

import pytest

from session_browser.web.renderers.markdown import render_markdown


# ─── Basic markdown to HTML ──────────────────────────────────────────

class TestBasicMarkdown:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_heading_h1(self):
        result = render_markdown("# Hello World")
        assert "<h1" in result
        assert "Hello World" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_heading_h2(self):
        result = render_markdown("## Section Title")
        assert "<h2" in result
        assert "Section Title" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_heading_h3(self):
        result = render_markdown("### Subsection")
        assert "<h3" in result
        assert "Subsection" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_bold_text(self):
        result = render_markdown("**bold text**")
        assert "<strong>" in result
        assert "bold text" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_italic_text(self):
        result = render_markdown("*italic text*")
        assert "<em>" in result
        assert "italic text" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_unordered_list(self):
        result = render_markdown("- item one\n- item two\n- item three")
        assert "<ul>" in result
        assert "<li>" in result
        assert "item one" in result
        assert "item two" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_ordered_list(self):
        result = render_markdown("1. first\n2. second\n3. third")
        assert "<ol>" in result
        assert "<li>" in result
        assert "first" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_paragraph(self):
        result = render_markdown("This is a plain paragraph.")
        assert "<p>" in result
        assert "This is a plain paragraph." in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_link(self):
        result = render_markdown("[click here](https://example.com)")
        assert "<a " in result
        assert "href=" in result
        assert "click here" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_inline_code(self):
        result = render_markdown("Use `print()` to output.")
        assert "<code>" in result
        assert "print()" in result


# ─── Code block rendering ─────────────────────────────────────────────

class TestCodeBlock:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_fenced_code_block(self):
        code = "```python\nprint('hello')\n```"
        result = render_markdown(code)
        assert "<pre>" in result
        assert "<code" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_code_block_preserves_content(self):
        code = "```\nline one\nline two\nline three\n```"
        result = render_markdown(code)
        assert "line one" in result
        assert "line two" in result
        assert "line three" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_code_block_with_language_hint(self):
        code = "```javascript\nconst x = 42;\n```"
        result = render_markdown(code)
        # markdown-it wraps language in the code element's class
        assert "<pre>" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_code_block_escapes_html(self):
        code = "```\n<div>hello</div>\n```"
        result = render_markdown(code)
        assert "<div>" not in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_backtick_fence(self):
        code = "```\nsimple code\n```"
        result = render_markdown(code)
        assert "<pre>" in result
        assert "simple code" in result


# ─── Table rendering ──────────────────────────────────────────────────

class TestTableRendering:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_basic_table(self):
        table = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |"
        result = render_markdown(table)
        assert "<table>" in result
        assert "<thead>" in result
        assert "<tbody>" in result
        assert "Alice" in result
        assert "Bob" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_table_headers(self):
        table = "| Col1 | Col2 |\n|------|------|\n| a | b |"
        result = render_markdown(table)
        assert "<th>" in result
        assert "Col1" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_table_cells(self):
        table = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = render_markdown(table)
        assert "<td>" in result
        assert "1" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_table_with_empty_cell(self):
        table = "| X | Y |\n|---|---|\n| | data |"
        result = render_markdown(table)
        assert "<table>" in result


# ─── XSS protection ───────────────────────────────────────────────────

class TestXSSProtection:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_script_tag_escaped(self):
        result = render_markdown('<script>alert("xss")</script>')
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_img_onerror_escaped(self):
        result = render_markdown('<img src=x onerror=alert(1)>')
        # After html.escape, < becomes &lt; so no raw HTML tag exists
        assert "<img " not in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_iframe_escaped(self):
        result = render_markdown('<iframe src="https://evil.com"></iframe>')
        assert "<iframe>" not in result
        assert "&lt;iframe" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_anchor_with_javascript_escaped(self):
        result = render_markdown('<a href="javascript:alert(1)">click</a>')
        # Tags are fully escaped; no raw <a tag
        assert "<a href=" not in result
        assert "&lt;a href=" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_event_handler_escaped(self):
        result = render_markdown('<div onclick="alert(1)">text</div>')
        # Tags are escaped; no raw <div tag
        assert "<div " not in result
        assert "&lt;div " in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_nested_html_escaped(self):
        result = render_markdown('<div><span><script>alert(1)</script></span></div>')
        assert "<script>" not in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_html_entity_in_markdown(self):
        # Existing HTML entities should be double-escaped or preserved safely
        result = render_markdown("5 &lt; 10")
        # After escaping, & becomes &amp;lt;
        assert "&amp;lt;" in result or "&lt;" in result


# ─── Empty input handling ─────────────────────────────────────────────

class TestEmptyInput:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_empty_string(self):
        assert render_markdown("") == ""

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_none_input(self):
        assert render_markdown(None) == ""

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_whitespace_only(self):
        result = render_markdown("   \n\t  ")
        # Whitespace-only may produce empty or whitespace HTML
        assert isinstance(result, str)

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_newlines_only(self):
        result = render_markdown("\n\n\n")
        assert isinstance(result, str)


# ─── Special character handling ───────────────────────────────────────

class TestSpecialCharacters:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_ampersand(self):
        result = render_markdown("A & B")
        assert "&amp;" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_less_than_greater_than(self):
        result = render_markdown("3 < 5 and 5 > 3")
        assert "&lt;" in result
        assert "&gt;" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_double_quotes(self):
        result = render_markdown('Say "hello"')
        assert "&quot;" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_single_quotes(self):
        result = render_markdown("It's a test")
        # Single quotes may or may not be escaped depending on html.escape settings
        assert isinstance(result, str)
        assert "test" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_unicode_characters(self):
        result = render_markdown("# 你好世界")
        assert "你好世界" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_emoji(self):
        result = render_markdown("# Hello :smile:")
        assert isinstance(result, str)

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_backslash(self):
        result = render_markdown("path\\to\\file")
        assert isinstance(result, str)

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_multiple_special_chars(self):
        result = render_markdown("<div> & \"quoted\" 'single'")
        assert "&lt;div&gt;" in result
        assert "&amp;" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_angle_brackets_in_paragraph(self):
        result = render_markdown("Use <Component /> in JSX")
        assert "&lt;Component" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_pipe_in_non_table_context(self):
        result = render_markdown("a | b | c")
        # Single row with pipes but no header separator should still produce table
        assert isinstance(result, str)

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_markdown_with_code_and_html(self):
        text = "Use `<script>` tag"
        result = render_markdown(text)
        assert "<code>" in result
        assert "<script>" not in result


# ─── Integration / edge cases ────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_mixed_markdown_and_escaped_html(self):
        text = "# Title\n\nSome **bold** and <b>raw</b> text."
        result = render_markdown(text)
        assert "<h1" in result
        assert "<strong>" in result
        assert "<b>" not in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_long_text(self):
        text = "a" * 10000
        result = render_markdown(text)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_multiline_heading(self):
        text = "## Line one\n## Line two"
        result = render_markdown(text)
        assert result.count("<h2") >= 2

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_empty_code_block(self):
        text = "```\n```"
        result = render_markdown(text)
        assert "<pre>" in result

    @pytest.mark.contract_case("DATA-PRESENTER-001")
    def test_nested_lists(self):
        text = "- item 1\n  - sub item\n- item 2"
        result = render_markdown(text)
        assert "<ul>" in result
        assert "<li>" in result
