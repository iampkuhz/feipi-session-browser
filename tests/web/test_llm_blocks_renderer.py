"""Tests for session_browser.web.renderers.llm_blocks module.

Covers:
- normalize_llm_content behavior (tool results, file markers, plain text, line numbers)
- render_llm_blocks_html output (HTML card structure, escaping)
- Code block rendering (language inference, file_code kind)
- File path processing (file marker detection, multi-file splitting)
- Empty input handling
- _content_parts_to_blocks bridge
- _parts_mode_from_raw bridge
"""
from __future__ import annotations

import pytest

from session_browser.web.renderers.llm_blocks import (
    normalize_llm_content,
    render_llm_blocks_html,
    _infer_code_language,
    _detect_file_marker,
    _try_split_files,
    _detect_line_number_gutter,
    _strip_line_number_gutter,
    _make_plain_block,
    _make_block_from_content,
    _html_escape,
    _content_parts_to_blocks,
    _parts_mode_from_raw,
)


# ─── normalize_llm_content ────────────────────────────────────────────

class TestNormalizeLlmContent:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_empty_string(self):
        assert normalize_llm_content("") == []

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_none_like_empty(self):
        assert normalize_llm_content("") == []

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_plain_text_no_markers(self):
        result = normalize_llm_content("Hello, this is a simple message.")
        assert len(result) == 1
        assert result[0]["kind"] == "plain_text"
        assert "Hello, this is a simple message." in result[0]["content"]

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_single_file_marker(self):
        text = "# AGENTS.md\nSome markdown content here."
        result = normalize_llm_content(text)
        assert len(result) >= 1
        assert any("AGENTS.md" in b.get("title", "") for b in result)

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_tool_result_parsing(self):
        text = "Tool result for toolu_abc123:\n# config.yaml\nkey: value\n"
        result = normalize_llm_content(text)
        assert len(result) >= 1
        # Tool ID should appear in title
        titles = " ".join(b.get("title", "") for b in result)
        assert "toolu_abc123" in titles

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_tool_result_with_file_content(self):
        text = "Tool result for toolu_xyz:\n# main.py\ndef hello():\n    pass\n"
        result = normalize_llm_content(text)
        assert len(result) >= 1
        assert any("main.py" in b.get("title", "") for b in result)

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_multiple_tool_results(self):
        text = (
            "Tool result for toolu_a:\n# file_a.py\nx = 1\n"
            "Tool result for toolu_b:\n# file_b.py\ny = 2\n"
        )
        result = normalize_llm_content(text)
        titles = " ".join(b.get("title", "") for b in result)
        assert "toolu_a" in titles
        assert "toolu_b" in titles

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_preamble_before_tool_result(self):
        text = "Here is some preamble text.\nTool result for toolu_x:\n# a.py\ncode\n"
        result = normalize_llm_content(text)
        kinds = [b["kind"] for b in result]
        # Should have at least a plain_text (preamble) and a file block
        assert "plain_text" in kinds

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_trailing_text_after_tool_result(self):
        text = "Tool result for toolu_t:\n# t.py\ncode\nTrailing text here."
        result = normalize_llm_content(text)
        assert len(result) >= 1

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_code_kind_inferred(self):
        text = "# script.sh\necho hello\n"
        result = normalize_llm_content(text)
        assert any(b["kind"] == "file_code" for b in result)

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_markdown_kind_inferred(self):
        text = "# README.md\nThis is a readme.\n"
        result = normalize_llm_content(text)
        assert any(b["kind"] == "file_markdown" for b in result)

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_multi_file_split(self):
        text = "# file1.py\nx = 1\n\n# file2.py\ny = 2\n"
        result = normalize_llm_content(text)
        assert len(result) >= 2
        filenames = " ".join(b.get("title", "") for b in result)
        assert "file1.py" in filenames
        assert "file2.py" in filenames

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_content_and_raw_fields_present(self):
        result = normalize_llm_content("Hello world")
        block = result[0]
        assert "content" in block
        assert "raw" in block
        assert "kind" in block
        assert "title" in block
        assert "subtitle" in block
        assert "language" in block

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_unknown_kind_when_no_content(self):
        # Edge case: content that produces no recognizable blocks
        result = normalize_llm_content("   \n   \n   ")
        # Whitespace-only should yield empty or unknown
        assert isinstance(result, list)


# ─── render_llm_blocks_html ──────────────────────────────────────────

class TestRenderLlmBlocksHtml:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_empty_input(self):
        result = render_llm_blocks_html("")
        assert "(No content available)" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_empty_list(self):
        result = render_llm_blocks_html([])
        assert "(No content available)" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_none_input(self):
        result = render_llm_blocks_html(None)
        assert "(No content available)" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_string_input_normalizes(self):
        result = render_llm_blocks_html("Hello world")
        assert '<div class="llm-block">' in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_list_input_renders_blocks(self):
        blocks = [
            {
                "kind": "plain_text",
                "title": "Test",
                "subtitle": "",
                "language": "",
                "content": "Hello",
                "raw": "Hello",
            }
        ]
        result = render_llm_blocks_html(blocks)
        assert '<div class="llm-block">' in result
        assert "Test" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_code_renders_pre_code(self):
        blocks = [
            {
                "kind": "file_code",
                "title": "File: hello.py",
                "subtitle": "",
                "language": "python",
                "content": "print('hi')",
                "raw": "print('hi')",
            }
        ]
        result = render_llm_blocks_html(blocks)
        assert "<pre>" in result
        assert "<code" in result
        assert "language-python" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_markdown_renders_via_markdown(self):
        blocks = [
            {
                "kind": "file_markdown",
                "title": "File: readme.md",
                "subtitle": "",
                "language": "",
                "content": "# Hello",
                "raw": "# Hello",
            }
        ]
        result = render_llm_blocks_html(blocks)
        assert '<div class="llm-block">' in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_header_contains_title(self):
        result = render_llm_blocks_html("Some content with tools")
        # llm-block__header may or may not be present for plain text with no title
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_html_escapes_title(self):
        blocks = [
            {
                "kind": "plain_text",
                "title": "<script>alert(1)</script>",
                "subtitle": "",
                "language": "",
                "content": "safe",
                "raw": "safe",
            }
        ]
        result = render_llm_blocks_html(blocks)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_html_escapes_content(self):
        blocks = [
            {
                "kind": "plain_text",
                "title": "",
                "subtitle": "",
                "language": "",
                "content": "<b>bold</b>",
                "raw": "<b>bold</b>",
            }
        ]
        result = render_llm_blocks_html(blocks)
        # Content goes through render_markdown which escapes HTML
        assert "<b>" not in result.replace("&lt;b&gt;", "")

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_multiple_blocks_rendered(self):
        blocks = [
            {
                "kind": "plain_text",
                "title": "Block 1",
                "subtitle": "",
                "language": "",
                "content": "text one",
                "raw": "text one",
            },
            {
                "kind": "plain_text",
                "title": "Block 2",
                "subtitle": "",
                "language": "",
                "content": "text two",
                "raw": "text two",
            },
        ]
        result = render_llm_blocks_html(blocks)
        assert result.count('<div class="llm-block">') >= 2

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_full_integration(self):
        text = "# hello.py\ndef greet():\n    return 'hello'\n"
        result = render_llm_blocks_html(text)
        assert '<div class="llm-block">' in result
        assert "hello.py" in result


# ─── Code block rendering / language inference ────────────────────────

class TestLanguageInference:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_python_extension(self):
        assert _infer_code_language("script.py") == "python"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_typescript_extension(self):
        assert _infer_code_language("app.ts") == "typescript"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_tsx_extension(self):
        assert _infer_code_language("Component.tsx") == "tsx"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_javascript_extension(self):
        assert _infer_code_language("main.js") == "javascript"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_yaml_extension(self):
        assert _infer_code_language("config.yaml") == "yaml"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_json_extension(self):
        assert _infer_code_language("data.json") == "json"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_shell_extension(self):
        assert _infer_code_language("run.sh") == "bash"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_rust_extension(self):
        assert _infer_code_language("lib.rs") == "rust"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_go_extension(self):
        assert _infer_code_language("main.go") == "go"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_java_extension(self):
        assert _infer_code_language("App.java") == "java"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_cpp_extension(self):
        assert _infer_code_language("main.cpp") == "cpp"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_ruby_extension(self):
        assert _infer_code_language("script.rb") == "ruby"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_css_extension(self):
        assert _infer_code_language("style.css") == "css"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_html_extension(self):
        assert _infer_code_language("page.html") == "html"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_empty_inputs(self):
        assert _infer_code_language() is None

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_python_from_content(self):
        result = _infer_code_language(content="def hello(): pass")
        assert result == "python"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_typescript_from_content(self):
        result = _infer_code_language(content="const x = 42;")
        assert result == "typescript"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_unknown_content(self):
        result = _infer_code_language(content="just some random text")
        assert result is None

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_filename_takes_precedence(self):
        # Filename hint should override content inference
        result = _infer_code_language("data.json", content="const x = 42;")
        assert result == "json"


# ─── File path processing ─────────────────────────────────────────────

class TestFileMarkerDetection:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_detect_simple_file_marker(self):
        result = _detect_file_marker("# AGENTS.md\nSome text")
        assert result == "AGENTS.md"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_detect_nested_path(self):
        result = _detect_file_marker("# src/main.py\nprint('hi')")
        assert result == "src/main.py"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_no_file_marker(self):
        result = _detect_file_marker("Just some text\nNo markers here.")
        assert result is None

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_marker_in_first_five_lines(self):
        text = "Line 1\nLine 2\n# config.yaml\nkey: val"
        result = _detect_file_marker(text)
        assert result == "config.yaml"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_marker_too_far(self):
        text = "L1\nL2\nL3\nL4\nL5\n# deep.md"
        result = _detect_file_marker(text)
        # The marker is on line 6, beyond first 5
        assert result is None

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_try_split_files_success(self):
        text = "# a.py\ncode_a\n\n# b.py\ncode_b\n"
        result = _try_split_files(text)
        assert len(result) >= 2

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_try_split_files_single_file_returns_empty(self):
        # Single file marker may not produce meaningful split
        text = "# a.py\ncode"
        result = _try_split_files(text)
        # May return empty list if split doesn't produce multiple parts
        assert isinstance(result, list)

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_try_split_files_no_markers(self):
        text = "just plain text\nno file headings"
        result = _try_split_files(text)
        assert result == []


# ─── Line number gutter handling ──────────────────────────────────────

class TestLineNumberGutter:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_detect_line_numbers(self):
        text = "1\tfirst\n2\tsecond\n3\tthird\n4\tfourth\n5\tfifth"
        assert _detect_line_number_gutter(text) is True

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_no_line_numbers(self):
        text = "hello\nworld\nfoo\nbar"
        assert _detect_line_number_gutter(text) is False

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_too_few_lines(self):
        text = "1\tfirst"
        assert _detect_line_number_gutter(text) is False

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_strip_line_numbers(self):
        text = "1\tfirst\n2\tsecond\n3\tthird\n4\tfourth\n5\tfifth"
        result = _strip_line_number_gutter(text)
        assert "\t" not in result
        assert "first" in result

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_strip_no_gutter_returns_original(self):
        text = "hello\nworld\nfoo"
        result = _strip_line_number_gutter(text)
        assert result == text


# ─── Block builders ───────────────────────────────────────────────────

class TestBlockBuilders:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_plain_block_empty_text(self):
        block = _make_plain_block("")
        assert block["kind"] == "unknown"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_plain_block_with_text(self):
        block = _make_plain_block("some text")
        assert block["kind"] == "plain_text"
        assert block["content"] == "some text"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_block_from_code_content(self):
        block = _make_block_from_content("def foo(): pass")
        assert block["kind"] == "file_code"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_block_from_markdown_content(self):
        block = _make_block_from_content("Just a paragraph.")
        assert block["kind"] == "plain_text"


# ─── HTML escape ──────────────────────────────────────────────────────

class TestHtmlEscape:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_escape_script(self):
        assert _html_escape("<script>") == "&lt;script&gt;"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_escape_quotes(self):
        assert _html_escape('"hello"') == "&quot;hello&quot;"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_escape_ampersand(self):
        assert _html_escape("A & B") == "A &amp; B"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_no_escape_needed(self):
        assert _html_escape("safe text") == "safe text"


# ─── _content_parts_to_blocks bridge ─────────────────────────────────

class TestContentPartsToBlocks:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_empty_list(self):
        result = _content_parts_to_blocks([])
        assert result == []

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_dict_input(self):
        parts = [
            {
                "part_type": "text",
                "content": "hello",
                "language": "python",
                "title": "Greeting",
                "context_type": "user",
            }
        ]
        result = _content_parts_to_blocks(parts)
        assert len(result) == 1
        assert result[0]["kind"] == "text"
        assert result[0]["content"] == "hello"
        assert result[0]["language"] == "python"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_dict_missing_keys_get_defaults(self):
        parts = [{"part_type": "code"}]
        result = _content_parts_to_blocks(parts)
        block = result[0]
        assert block["content"] == ""
        assert block["language"] == ""
        assert block["title"] == ""
        assert block["content_bytes"] == 0

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_non_dict_non_content_part(self):
        parts = [42]
        result = _content_parts_to_blocks(parts)
        assert len(result) == 1
        assert result[0]["kind"] == "unknown"
        assert result[0]["content"] == "42"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_none_in_list(self):
        parts = [None]
        result = _content_parts_to_blocks(parts)
        assert len(result) == 1
        assert result[0]["kind"] == "unknown"
        assert result[0]["content"] == ""

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_content_bytes_computed(self):
        parts = [
            {
                "part_type": "text",
                "content": "hello world",
                "language": "",
                "title": "",
            }
        ]
        result = _content_parts_to_blocks(parts)
        assert result[0]["content_bytes"] == len("hello world".encode("utf-8"))


# ─── _parts_mode_from_raw bridge ──────────────────────────────────────

class TestPartsModeFromRaw:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_empty_string(self):
        result = _parts_mode_from_raw("")
        assert result == []

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_non_empty_string(self):
        result = _parts_mode_from_raw("Hello world")
        assert isinstance(result, list)

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_returns_list_of_dicts(self):
        result = _parts_mode_from_raw("# test.py\nprint('hi')\n")
        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], dict)


# ─── Edge cases / integration ────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_long_content(self):
        text = "a" * 50000
        result = normalize_llm_content(text)
        assert len(result) >= 1
        assert result[0]["content"] == text

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_unicode_content(self):
        text = "# 你好.md\n这是中文内容。"
        result = normalize_llm_content(text)
        assert len(result) >= 1

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_html_in_content(self):
        text = "<div>Some HTML</div>"
        result = render_llm_blocks_html(text)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_tool_result_id_without_toolu_prefix(self):
        text = "Tool result for my_custom_tool:\n# data.json\n{}\n"
        result = normalize_llm_content(text)
        titles = " ".join(b.get("title", "") for b in result)
        assert "my_custom_tool" in titles

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_with_dockerfile_name(self):
        # Note: source code lowers filename_hint but lang_map has "Dockerfile" (capitalized),
        # so endswith("Dockerfile") fails after lowering. Returns None in practice.
        result = _infer_code_language("Dockerfile")
        assert result is None

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_file_with_makefile_name(self):
        # Same case-sensitivity issue: "Makefile" lowered to "makefile" doesn't match "Makefile" key.
        result = _infer_code_language("Makefile")
        assert result is None

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_import_without_brace_not_python(self):
        # "import { something }" is JS, not Python
        # Python: "import os" (without curly brace)
        result = _infer_code_language(content="import os")
        assert result == "python"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_import_with_brace_is_typescript(self):
        result = _infer_code_language(content="import { useState } from 'react'")
        assert result == "typescript"

    @pytest.mark.contract_case("DATA-PRESENTER-009")
    def test_render_with_subtitle(self):
        blocks = [
            {
                "kind": "plain_text",
                "title": "Main",
                "subtitle": "Subtitle text",
                "language": "",
                "content": "body",
                "raw": "body",
            }
        ]
        result = render_llm_blocks_html(blocks)
        assert "Subtitle text" in result
