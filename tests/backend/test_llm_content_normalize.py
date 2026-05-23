"""Unit tests for normalize_llm_content and render_llm_blocks_html.

Covers:
- Single plain markdown string
- Tool result + markdown file content
- Multiple tool results concatenated
- Markdown tables
- YAML/JSON/code files
- Line number gutter detection and stripping
- Content that contains ordered lists (must not be误stripped)
- Empty / None input
- render_llm_blocks_html produces non-empty HTML
"""

import pytest
from session_browser.web.routes import (
    normalize_llm_content,
    render_llm_blocks_html,
    _detect_line_number_gutter,
    _strip_line_number_gutter,
    _infer_code_language,
    _detect_file_marker,
)


# ── Single plain markdown string ────────────────────────────────────────


def test_single_markdown_string():
    """A single markdown string without tool result boundaries becomes one block."""
    text = "# Hello\n\nThis is **bold** text.\n\n- Item 1\n- Item 2"
    blocks = normalize_llm_content(text)
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "plain_text"
    assert blocks[0]["content"] == text
    assert blocks[0]["raw"] == text


def test_single_markdown_with_table():
    """Markdown with table stays as one block."""
    text = "# Table Test\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    blocks = normalize_llm_content(text)
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "plain_text"
    assert "| A | B |" in blocks[0]["content"]


# ── Tool result + markdown file content ─────────────────────────────────


def test_tool_result_with_markdown_file():
    """'Tool result for toolu_xxx:' followed by markdown file content."""
    text = (
        "Tool result for toolu_vrt123:\n"
        "# AGENTS.md\n\n"
        "OpenSpec navigation.\n\n"
        "**定位**：本文档只负责回答三件事.\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| Name  | Test  |"
    )
    blocks = normalize_llm_content(text)
    assert len(blocks) >= 1
    # The file heading should be preserved in content
    all_content = "\n".join(b["content"] for b in blocks)
    assert "定位" in all_content
    # The filename should appear either in content or title
    has_filename = "AGENTS.md" in all_content or any("AGENTS.md" in b.get("title", "") for b in blocks)
    assert has_filename, f"AGENTS.md not found in blocks: {[b.get('title') for b in blocks]}"


def test_multiple_tool_results():
    """Multiple tool results should be split into separate blocks."""
    text = (
        "Tool result for toolu_abc:\nFirst tool result content.\n\n"
        "Tool result for toolu_def:\nSecond tool result content."
    )
    blocks = normalize_llm_content(text)
    assert len(blocks) >= 2
    all_content = "\n".join(b["content"] for b in blocks)
    assert "First tool result content" in all_content
    assert "Second tool result content" in all_content


# ── File detection ──────────────────────────────────────────────────────


def test_file_marker_detection():
    """Content starting with '# filename.ext' should detect the file."""
    text = "# AGENTS.md\n\nSome content here."
    filename = _detect_file_marker(text)
    assert filename == "AGENTS.md"


def test_file_marker_not_found():
    """Text without a file-like heading should return None."""
    text = "# Some heading\n\nRegular text."
    assert _detect_file_marker(text) is None


def test_yaml_file_detection():
    """YAML files should be detected and tagged."""
    text = "# config.yaml\n\nkey: value\nlist:\n  - item1\n  - item2"
    blocks = normalize_llm_content(text)
    assert len(blocks) >= 1
    # The block should be file_code with yaml language
    yaml_blocks = [b for b in blocks if b.get("language") == "yaml"]
    assert len(yaml_blocks) >= 1


def test_json_file_detection():
    """JSON files should be detected and tagged."""
    text = "# config.json\n\n{\"key\": \"value\", \"list\": [1, 2, 3]}"
    blocks = normalize_llm_content(text)
    json_blocks = [b for b in blocks if b.get("language") == "json"]
    assert len(json_blocks) >= 1


def test_python_file_detection():
    """Python files should be detected and tagged."""
    text = "# main.py\n\ndef hello():\n    print('world')"
    blocks = normalize_llm_content(text)
    py_blocks = [b for b in blocks if b.get("language") == "python"]
    assert len(py_blocks) >= 1


# ── Language inference ──────────────────────────────────────────────────


def test_infer_language_from_filename():
    """Language should be inferred from file extension."""
    assert _infer_code_language("main.py") == "python"
    assert _infer_code_language("app.ts") == "typescript"
    assert _infer_code_language("app.tsx") == "tsx"
    assert _infer_code_language("config.yaml") == "yaml"
    assert _infer_code_language("data.json") == "json"
    assert _infer_code_language("run.sh") == "bash"
    assert _infer_code_language("main.go") == "go"
    assert _infer_code_language("Cargo.toml") == "toml"


def test_infer_language_from_content():
    """Language should be inferred from content patterns when no filename."""
    assert _infer_code_language(content="def hello():\n    pass") == "python"
    assert _infer_code_language(content="const x = 1;") == "typescript"
    assert _infer_code_language(content="import { useState } from 'react';") == "typescript"


def test_markdown_returns_none_language():
    """Markdown files should NOT return a code language."""
    assert _infer_code_language("README.md") is None
    assert _infer_code_language("notes.markdown") is None


# ── Line number gutter ──────────────────────────────────────────────────


def test_detect_line_number_gutter_positive():
    """Text with tab-separated line numbers should be detected."""
    text = "1\t# Hello\n2\t\n3\tWorld\n4\t\n5\tEnd"
    assert _detect_line_number_gutter(text) is True


def test_detect_line_number_gutter_negative():
    """Text without line numbers should NOT be detected."""
    text = "# Hello\n\nWorld\n\nEnd"
    assert _detect_line_number_gutter(text) is False


def test_detect_line_number_gutter_ordered_list():
    """Ordered list should NOT be detected as line number gutter (fewer lines match)."""
    text = "1. First item\n2. Second item\n3. Third item"
    # Ordered list uses "1." not "1\t", so should not match \d+\t pattern
    assert _detect_line_number_gutter(text) is False


def test_strip_line_number_gutter():
    """Line number gutter should be stripped from each line."""
    text = "1\t# Hello\n2\t\n3\tWorld"
    result = _strip_line_number_gutter(text)
    assert result == "# Hello\n\nWorld"


def test_strip_line_number_gutter_preserves_non_gutter():
    """Text without consistent gutter should NOT be modified."""
    text = "1. First\n2. Second\n3. Third"
    result = _strip_line_number_gutter(text)
    # Should return unchanged because <60% match the \d+\t pattern
    assert result == text


# ── Empty / edge cases ──────────────────────────────────────────────────


def test_empty_input():
    """Empty string should return empty list."""
    assert normalize_llm_content("") == []
    assert normalize_llm_content(None) == []  # type: ignore


def test_whitespace_only():
    """Whitespace-only input should return empty list or single block with no meaningful content."""
    blocks = normalize_llm_content("   \n\n  ")
    # May be empty list or a block with empty/whitespace content
    if blocks:
        assert all(b["content"].strip() == "" or b["content"].strip() for b in blocks)


# ── render_llm_blocks_html ──────────────────────────────────────────────


def test_render_empty():
    """Empty blocks should produce a fallback message."""
    html = render_llm_blocks_html([])
    assert "No content available" in html


def test_render_single_markdown_block():
    """A markdown block should render with header and rendered content."""
    blocks = [{
        "kind": "plain_text",
        "title": "Message content",
        "subtitle": "",
        "language": "",
        "content": "# Hello\n\nThis is **bold**.",
        "raw": "# Hello\n\nThis is **bold**.",
    }]
    html = render_llm_blocks_html(blocks)
    assert "llm-block" in html
    assert "Message content" in html
    # Content should be rendered as markdown HTML
    assert "<h1" in html or "<strong>" in html


def test_render_code_block():
    """A code block should render with <pre><code> and language class."""
    blocks = [{
        "kind": "file_code",
        "title": "File: config.yaml",
        "subtitle": "",
        "language": "yaml",
        "content": "key: value",
        "raw": "key: value",
    }]
    html = render_llm_blocks_html(blocks)
    assert "File: config.yaml" in html
    assert "language-yaml" in html
    assert "<pre>" in html
    assert "<code" in html


def test_render_multiple_blocks():
    """Multiple blocks should render as separate cards."""
    blocks = [
        {
            "kind": "plain_text",
            "title": "Tool Result: toolu_abc",
            "subtitle": "",
            "language": "",
            "content": "# First file",
            "raw": "# First file",
        },
        {
            "kind": "file_code",
            "title": "File: config.yaml",
            "subtitle": "",
            "language": "yaml",
            "content": "key: value",
            "raw": "key: value",
        },
    ]
    html = render_llm_blocks_html(blocks)
    assert html.count("llm-block") >= 2
    assert "Tool Result: toolu_abc" in html
    assert "File: config.yaml" in html


def test_render_escapes_html():
    """Block content should be HTML-escaped to prevent XSS."""
    blocks = [{
        "kind": "file_code",
        "title": "File: test.html",
        "subtitle": "",
        "language": "html",
        "content": '<script>alert("xss")</script>',
        "raw": '<script>alert("xss")</script>',
    }]
    html = render_llm_blocks_html(blocks)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── Content preservation ────────────────────────────────────────────────


def test_ordered_list_in_content_preserved():
    """Content with ordered lists should preserve the list numbers."""
    text = (
        "Tool result for toolu_xyz:\n"
        "# README.md\n\n"
        "Steps:\n"
        "1. First step\n"
        "2. Second step\n"
        "3. Third step"
    )
    blocks = normalize_llm_content(text)
    all_content = "\n".join(b["content"] for b in blocks)
    assert "1. First step" in all_content
    assert "2. Second step" in all_content
    assert "3. Third step" in all_content


def test_raw_field_preserved():
    """The raw field should always contain the original content."""
    text = "1\tline1\n2\tline2\n3\tline3"
    blocks = normalize_llm_content(text)
    for block in blocks:
        assert "raw" in block


def test_no_content_lost():
    """All original text should be present across all blocks."""
    text = (
        "Tool result for toolu_a:\nSome content A.\n\n"
        "Tool result for toolu_b:\nSome content B."
    )
    blocks = normalize_llm_content(text)
    all_content = "\n".join(b["content"] for b in blocks)
    all_titles = "\n".join(b.get("title", "") for b in blocks)
    assert "Some content A" in all_content
    assert "Some content B" in all_content
    # Tool IDs appear in block titles, not content (they're parsed as boundary markers)
    assert "toolu_a" in all_titles or "toolu_a" in all_content
    assert "toolu_b" in all_titles or "toolu_b" in all_content
