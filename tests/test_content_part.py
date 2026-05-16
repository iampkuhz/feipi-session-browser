"""Unit tests for ContentPart detection functions.

Covers:
- is_json detects valid JSON objects and arrays
- is_image_url detects HTTP URLs, data URIs, markdown image syntax
- is_html detects HTML documents but not inline tags in prose
- is_code_block detects fenced code, file extensions, code patterns
- detect_content_type returns correct type for common payloads
- Backward compatibility: from_text wraps plain strings as markdown
- Empty/None handling
"""

import pytest
from session_browser.domain.content_part import (
    ContentPart,
    ContentPartType,
    is_json,
    is_image_url,
    is_html,
    is_code_block,
    detect_content_type,
)


# ─── is_json ──────────────────────────────────────────────────────────────


def test_is_json_object():
    assert is_json('{"key": "value"}') is True


def test_is_json_array():
    assert is_json('[1, 2, 3]') is True


def test_is_json_nested():
    assert is_json('{"a": {"b": [1, 2]}}') is True


def test_is_json_with_leading_whitespace():
    assert is_json('  {"key": "value"}') is True


def test_is_json_invalid():
    assert is_json('{"key": }') is False
    assert is_json('[1, 2,]') is False
    assert is_json('not json') is False
    assert is_json('') is False


def test_is_json_markdown_not_json():
    assert is_json('# Hello\n\nThis is text.') is False


def test_is_json_ordered_list_not_json():
    assert is_json('1. First\n2. Second') is False


# ─── is_image_url ─────────────────────────────────────────────────────────


def test_is_image_url_png():
    assert is_image_url('https://example.com/diagram.png') is True


def test_is_image_url_jpg():
    assert is_image_url('https://example.com/photo.jpg') is True


def test_is_image_url_gif():
    assert is_image_url('https://example.com/anim.gif') is True


def test_is_image_url_webp():
    assert is_image_url('https://example.com/image.webp') is True


def test_is_image_url_with_query_params():
    assert is_image_url('https://example.com/img.png?token=abc') is True


def test_is_image_data_uri():
    assert is_image_url('data:image/png;base64,iVBORw0KGgo') is True


def test_is_image_markdown_syntax():
    assert is_image_url('![alt text](https://example.com/img.png)') is True


def test_is_image_url_negative():
    assert is_image_url('https://example.com/page.html') is False
    assert is_image_url('https://example.com/data.json') is False
    assert is_image_url('') is False
    assert is_image_url('just some text') is False


# ─── is_html ──────────────────────────────────────────────────────────────


def test_is_html_full_document():
    assert is_html('<!DOCTYPE html>\n<html><body>Hello</body></html>') is True


def test_is_html_table():
    assert is_html('<table><tr><td>Cell</td></tr></table>') is True


def test_is_html_comment():
    assert is_html('<!-- This is a comment -->\n<div>Content</div>') is True


def test_is_html_with_whitespace():
    assert is_html('  \n<div class="container">Hello</div>') is True


def test_is_html_inline_tag_in_prose_not_detected():
    """Short text with single inline tag should NOT be HTML."""
    assert is_html('Use <code> for inline code.') is False


def test_is_html_empty():
    assert is_html('') is False


def test_is_html_plain_text():
    assert is_html('# Heading\n\nSome markdown text.') is False


# ─── is_code_block ────────────────────────────────────────────────────────


def test_is_code_fenced():
    assert is_code_block('```python\ndef hello():\n    pass\n```') is True


def test_is_code_python_def():
    assert is_code_block('def hello():\n    print("world")') is True


def test_is_code_python_class():
    assert is_code_block('class MyClass:\n    pass') is True


def test_is_code_python_import():
    assert is_code_block('from os import path') is True


def test_is_code_typescript():
    assert is_code_block('const x = 1;\nexport default x;') is True


def test_is_code_go():
    assert is_code_block('package main\n\nfunc main() {}') is True


def test_is_code_rust():
    assert is_code_block('pub fn main() {\n    println!("hello");\n}') is True


def test_is_code_with_filename():
    assert is_code_block('x = 1\nprint(x)', filename_hint='script.py') is True


def test_is_code_markdown_file_not_code():
    assert is_code_block('# README\n\nSome docs.', filename_hint='README.md') is False


def test_is_code_prose_not_code():
    assert is_code_block('Hello world, this is a normal paragraph.') is False


def test_is_code_empty():
    assert is_code_block('') is False


# ─── detect_content_type ──────────────────────────────────────────────────


def test_detect_empty():
    assert detect_content_type('') == ContentPartType.TEXT
    assert detect_content_type('   \n\n  ') == ContentPartType.TEXT


def test_detect_markdown():
    result = detect_content_type('# Hello\n\nThis is **bold** text.')
    assert result == ContentPartType.MARKDOWN


def test_detect_json():
    result = detect_content_type('{"status": "ok", "count": 5}')
    assert result == ContentPartType.JSON


def test_detect_image():
    result = detect_content_type('https://example.com/diagram.png')
    assert result == ContentPartType.IMAGE


def test_detect_code():
    result = detect_content_type('def hello():\n    print("world")')
    assert result == ContentPartType.CODE


def test_detect_code_with_filename():
    result = detect_content_type('x = 1', filename_hint='main.py')
    assert result == ContentPartType.CODE


def test_detect_html():
    result = detect_content_type('<table><tr><td>Cell</td></tr></table>')
    assert result == ContentPartType.HTML


def test_detect_ordered_list_not_code():
    """Ordered list should NOT be detected as code."""
    result = detect_content_type('1. First step\n2. Second step\n3. Third step')
    assert result == ContentPartType.MARKDOWN


# ─── ContentPart model ────────────────────────────────────────────────────


def test_from_text_empty():
    part = ContentPart.from_text('')
    assert part.part_type == ContentPartType.TEXT
    assert part.content == ''


def test_from_text_whitespace_only():
    part = ContentPart.from_text('   \n\n  ')
    assert part.part_type == ContentPartType.TEXT


def test_from_text_normal():
    part = ContentPart.from_text('# Hello\n\n**World**')
    assert part.part_type == ContentPartType.MARKDOWN
    assert '# Hello' in part.content


def test_from_text_json_becomes_markdown():
    """from_text should always produce markdown for non-empty text.

    The detection is in detect_content_type; from_text is a simple
    backward-compat wrapper.
    """
    part = ContentPart.from_text('{"key": "value"}')
    # from_text wraps as markdown (not json) — that's the backward-compat behavior
    assert part.part_type == ContentPartType.MARKDOWN


def test_content_part_properties():
    part = ContentPart(part_type=ContentPartType.CODE, content='x=1', language='python')
    assert part.is_code is True
    assert part.is_text is False
    assert part.is_markdown is False
    assert part.is_json is False
    assert part.is_image is False
    assert part.is_html is False


def test_content_part_serialization():
    part = ContentPart(
        part_type=ContentPartType.CODE,
        content='print(1)',
        language='python',
        filename='test.py',
        metadata={'line_count': 1},
    )
    d = part.to_dict()
    assert d['part_type'] == 'code'
    assert d['language'] == 'python'
    assert d['filename'] == 'test.py'
    assert d['metadata']['line_count'] == 1

    restored = ContentPart.from_dict(d)
    assert restored.part_type == part.part_type
    assert restored.content == part.content
    assert restored.language == part.language
    assert restored.filename == part.filename


def test_content_part_type_constants():
    assert ContentPartType.TEXT == 'text'
    assert ContentPartType.MARKDOWN == 'markdown'
    assert ContentPartType.JSON == 'json'
    assert ContentPartType.IMAGE == 'image'
    assert ContentPartType.CODE == 'code'
    assert ContentPartType.HTML == 'html'


# ─── I-08 ContextPartType constants ────────────────────────────────────


def test_context_part_type_constants():
    from session_browser.domain.content_part import ContextPartType
    assert ContextPartType.SYSTEM_PROMPT == 'system_prompt'
    assert ContextPartType.USER_MESSAGE == 'user_message'
    assert ContextPartType.ASSISTANT_MESSAGE == 'assistant_message'
    assert ContextPartType.TOOL_RESULT == 'tool_result'
    assert ContextPartType.TOOL_USE == 'tool_use'
    assert ContextPartType.ATTACHMENT == 'attachment'
    assert ContextPartType.IMAGE_CONTENT == 'image_content'
    assert ContextPartType.DOCUMENT_CONTENT == 'document_content'
    assert ContextPartType.UNKNOWN == 'unknown'


# ─── I-08 New ContentPart fields ───────────────────────────────────────


def test_content_part_new_fields_defaults():
    """New multipart fields should default to sensible values."""
    part = ContentPart(part_type="text", content="hello")
    from session_browser.domain.content_part import ContextPartType
    assert part.context_type == ContextPartType.UNKNOWN
    assert part.title == ""
    assert part.content_bytes == 0
    assert part.token_hint == 0


def test_content_part_new_fields_set():
    part = ContentPart(
        part_type="markdown",
        content="Hello world",
        context_type="user_message",
        title="User Message #1",
    )
    assert part.context_type == "user_message"
    assert part.title == "User Message #1"


def test_content_part_context_type_properties():
    from session_browser.domain.content_part import ContextPartType
    part = ContentPart(part_type="markdown", content="test", context_type=ContextPartType.SYSTEM_PROMPT)
    assert part.is_system_prompt is True
    assert part.is_user_message is False
    assert part.is_tool_result is False
    assert part.is_attachment is False

    part2 = ContentPart(part_type="text", content="test", context_type=ContextPartType.USER_MESSAGE)
    assert part2.is_user_message is True

    part3 = ContentPart(part_type="json", content="{}", context_type=ContextPartType.TOOL_RESULT)
    assert part3.is_tool_result is True


def test_content_part_compute_metadata():
    part = ContentPart(part_type="markdown", content="Hello world, this is a test.")
    assert part.content_bytes == 0  # Not yet computed
    assert part.token_hint == 0

    part.compute_metadata()
    assert part.content_bytes > 0
    assert part.token_hint > 0
    # 31 chars / 4 = ~7 tokens (heuristic)
    assert part.token_hint == max(1, 31 // 4)


def test_content_part_compute_metadata_preserves_existing():
    """If bytes/token are already set, compute_metadata should not overwrite."""
    part = ContentPart(
        part_type="markdown",
        content="Hello",
        content_bytes=100,
        token_hint=25,
    )
    part.compute_metadata()
    assert part.content_bytes == 100
    assert part.token_hint == 25


def test_content_part_compute_all():
    parts = [
        ContentPart(part_type="text", content="a"),
        ContentPart(part_type="markdown", content="Hello world"),
    ]
    ContentPart.compute_all(parts)
    for p in parts:
        assert p.content_bytes > 0 or p.content == ""
        assert p.token_hint >= 0


def test_content_part_serialization_includes_new_fields():
    part = ContentPart(
        part_type="markdown",
        content="test",
        context_type="user_message",
        title="User #1",
        content_bytes=4,
        token_hint=1,
    )
    d = part.to_dict()
    assert d["context_type"] == "user_message"
    assert d["title"] == "User #1"
    assert d["content_bytes"] == 4
    assert d["token_hint"] == 1

    restored = ContentPart.from_dict(d)
    assert restored.context_type == part.context_type
    assert restored.title == part.title
    assert restored.content_bytes == part.content_bytes
    assert restored.token_hint == part.token_hint
