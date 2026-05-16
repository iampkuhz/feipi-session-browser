"""Unit tests for normalize_message_content.

Covers:
- Empty / None input returns a single empty text part.
- Whitespace-only input.
- Simple markdown text.
- Fenced code blocks with various languages.
- JSON objects and arrays (standalone and embedded).
- Mixed content (markdown + code + JSON).
- Multiple code blocks in one message.
- Unclosed / partial fences (fallback to markdown).
- Idempotency: running twice yields the same result.
- Content preservation: no original text is lost.
- Backward compatibility: from_text bridge.
"""

import json
import pytest

from session_browser.domain.normalizer import normalize_message_content
from session_browser.domain.content_part import ContentPart, ContentPartType


# ─── Empty / None input ───────────────────────────────────────────────────

def test_none_input():
    parts = normalize_message_content(None)
    assert isinstance(parts, list)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT
    assert parts[0].content == ""


def test_empty_string():
    parts = normalize_message_content("")
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT
    assert parts[0].content == ""


def test_whitespace_only():
    parts = normalize_message_content("   \n\n  \t  ")
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT


# ─── Simple markdown ─────────────────────────────────────────────────────

def test_simple_markdown():
    text = "# Hello\n\nThis is **bold** text.\n\n- Item 1\n- Item 2"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.MARKDOWN
    assert "# Hello" in parts[0].content


def test_markdown_with_table():
    text = "| A | B |\n|---|---|\n| 1 | 2 |"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.MARKDOWN


# ─── Fenced code blocks ──────────────────────────────────────────────────

def test_python_code_block():
    text = "```python\ndef hello():\n    print('world')\n```"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == "python"
    assert "def hello():" in parts[0].content


def test_typescript_code_block():
    text = "```typescript\nconst x: number = 1;\n```"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == "typescript"


def test_code_block_no_language():
    text = "```\nsome code here\n```"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == ""
    assert "some code here" in parts[0].content


def test_tilde_fence():
    text = "~~~bash\necho hello\n~~~"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == "bash"


def test_multiple_code_blocks():
    text = (
        "Here is some Python:\n\n"
        "```python\ndef foo(): pass\n```\n\n"
        "And here is some JS:\n\n"
        "```javascript\nconsole.log('hi');\n```"
    )
    parts = normalize_message_content(text)
    code_parts = [p for p in parts if p.part_type == ContentPartType.CODE]
    md_parts = [p for p in parts if p.part_type == ContentPartType.MARKDOWN]
    assert len(code_parts) == 2
    assert code_parts[0].language == "python"
    assert code_parts[1].language == "javascript"
    assert len(md_parts) >= 1


def test_unclosed_fence_with_language():
    """Unclosed code fence with language is still detected (fence pattern match)."""
    text = "```python\ndef broken():"
    parts = normalize_message_content(text)
    # Detected as code because content starts with ``` and has code patterns.
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    # Language extracted from the opening fence line.
    assert parts[0].language == "python"
    assert "def broken():" in parts[0].content


def test_unclosed_fence_prose():
    """Unclosed fence with prose is still detected as code (fence pattern match)."""
    text = "```\nThis is just plain text, not code.\nNo functions or classes here."
    parts = normalize_message_content(text)
    # Detected as code because content starts with ``` (fenced code pattern).
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE


# ─── JSON ────────────────────────────────────────────────────────────────

def test_standalone_json_object():
    text = '{"status": "ok", "count": 5}'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON
    assert '"status"' in parts[0].content


def test_standalone_json_array():
    text = '[1, 2, {"name": "test"}]'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON


def test_nested_json():
    text = '{"a": {"b": [1, 2, 3], "c": {"d": "e"}}}'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON


def test_json_with_whitespace():
    text = '\n  {"key": "value"}\n'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON


# ─── Mixed content ───────────────────────────────────────────────────────

def test_markdown_then_code():
    text = "Here's the function:\n\n```python\ndef hello():\n    pass\n```"
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.MARKDOWN in types
    assert ContentPartType.CODE in types


def test_code_then_markdown():
    text = "```python\nx = 1\n```\n\nThis sets x to 1."
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.CODE in types
    assert ContentPartType.MARKDOWN in types


def test_json_embedded_in_markdown():
    """JSON separated by blank lines from surrounding text."""
    text = (
        "The API returned this response:\n\n"
        '{"status": "ok", "data": [1, 2, 3]}\n\n'
        "Which means everything is fine."
    )
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.JSON in types
    assert ContentPartType.MARKDOWN in types


def test_complex_mixed():
    """Markdown + code + JSON + more markdown."""
    text = (
        "Let me show you the config:\n\n"
        "```yaml\nname: test\nversion: 1\n```\n\n"
        "The response was:\n\n"
        '{"result": "success"}\n\n'
        "That's all."
    )
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.CODE in types
    assert ContentPartType.JSON in types
    assert ContentPartType.MARKDOWN in types
    # Should have at least 4 parts (md + code + md + json + md)
    assert len(parts) >= 4


# ─── Content preservation ────────────────────────────────────────────────

def test_no_content_lost_simple():
    """All original text should be present in the output."""
    text = "Hello world\n\n```python\nx = 1\n```\n\nDone."
    parts = normalize_message_content(text)
    all_content = " ".join(p.content for p in parts)
    assert "Hello world" in all_content
    assert "x = 1" in all_content
    assert "Done." in all_content


def test_no_content_lost_json():
    text = 'Intro\n\n{"key": "value"}\n\nOutro'
    parts = normalize_message_content(text)
    all_content = " ".join(p.content for p in parts)
    assert "Intro" in all_content
    assert '"key"' in all_content
    assert '"value"' in all_content
    assert "Outro" in all_content


# ─── Idempotency ──────────────────────────────────────────────────────────

def test_idempotent_markdown():
    """Running on a markdown part's content again yields the same type."""
    text = "# Hello\n\nWorld"
    parts1 = normalize_message_content(text)
    # Re-normalize the combined content
    combined = parts1[0].content
    parts2 = normalize_message_content(combined)
    assert len(parts1) == len(parts2)
    assert parts1[0].part_type == parts2[0].part_type


def test_idempotent_code():
    code = "def foo():\n    pass"
    part = ContentPart(
        part_type=ContentPartType.CODE,
        content=code,
        language="python",
    )
    parts = normalize_message_content(part.content)
    # The code without fence should be detected as code by content patterns
    code_parts = [p for p in parts if p.part_type == ContentPartType.CODE]
    assert len(code_parts) >= 1


# ─── Edge cases ──────────────────────────────────────────────────────────

def test_json_array_at_start():
    text = '[{"id": 1}]\n\nHere is an explanation.'
    parts = normalize_message_content(text)
    assert parts[0].part_type == ContentPartType.JSON


def test_code_block_with_json_inside():
    """JSON inside a code block should be part of the code, not separate."""
    text = '```json\n{"key": "value"}\n```'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == "json"


def test_empty_lines_between_code_blocks():
    text = "```python\na = 1\n```\n\n\n```python\nb = 2\n```"
    parts = normalize_message_content(text)
    code_parts = [p for p in parts if p.part_type == ContentPartType.CODE]
    assert len(code_parts) == 2


def test_single_line_code():
    text = "`inline code`"
    parts = normalize_message_content(text)
    # Single backtick is not a fence, should be markdown
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.MARKDOWN


def test_long_fence():
    """Fences with more than 3 backticks should work."""
    text = "````python\ncode here\n````"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == "python"


def test_invalid_json_fallback():
    """Text that looks like JSON but isn't valid should be markdown."""
    text = '{"key": }'
    parts = normalize_message_content(text)
    # Invalid JSON should fall back to markdown
    assert all(p.part_type != ContentPartType.JSON for p in parts)


def test_output_is_list_of_contentpart():
    """Output must be list of ContentPart instances."""
    parts = normalize_message_content("test content")
    assert isinstance(parts, list)
    for p in parts:
        assert isinstance(p, ContentPart)


def test_content_part_has_no_empty_metadata():
    """ContentParts should have default empty metadata."""
    parts = normalize_message_content("test")
    for p in parts:
        assert isinstance(p.metadata, dict)
        assert isinstance(p.language, str)
        assert isinstance(p.filename, str)


# ─── I-08 normalize_context_parts ──────────────────────────────────────


from session_browser.domain.normalizer import (
    normalize_context_parts,
    detect_multipart_messages,
)
from session_browser.domain.content_part import ContextPartType


def test_normalize_context_parts_none():
    parts = normalize_context_parts(None)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT
    assert parts[0].content == ""
    assert parts[0].content_bytes == 0


def test_normalize_context_parts_empty():
    parts = normalize_context_parts("")
    assert len(parts) == 1
    assert parts[0].context_type == ContextPartType.UNKNOWN


def test_normalize_context_parts_sets_type_and_title():
    parts = normalize_context_parts(
        "Hello world",
        default_context_type=ContextPartType.USER_MESSAGE,
        title="User Message #1",
    )
    assert len(parts) >= 1
    for p in parts:
        assert p.context_type == ContextPartType.USER_MESSAGE
        assert p.title == "User Message #1"
        # Metadata should be auto-computed.
        assert p.content_bytes > 0 or p.content == ""
        assert p.token_hint >= 0


def test_normalize_context_parts_markdown_with_code():
    text = "Here is code:\n\n```python\nx = 1\n```\n\nDone."
    parts = normalize_context_parts(
        text,
        default_context_type=ContextPartType.ASSISTANT_MESSAGE,
        title="Assistant #1",
    )
    # Should have at least 2 parts (markdown intro + code).
    assert len(parts) >= 2
    types = [p.part_type for p in parts]
    assert ContentPartType.CODE in types
    assert ContentPartType.MARKDOWN in types
    # All parts should have the same context_type and title.
    for p in parts:
        assert p.context_type == ContextPartType.ASSISTANT_MESSAGE
        assert p.title == "Assistant #1"


# ─── I-08 detect_multipart_messages ────────────────────────────────────


def test_detect_multipart_not_json():
    """Plain text should return empty list (not a messages array)."""
    result = detect_multipart_messages("Hello world")
    assert result == []


def test_detect_multipart_empty():
    assert detect_multipart_messages("") == []
    assert detect_multipart_messages("   ") == []


def test_detect_multipart_valid_messages_array():
    text = '[{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Hi!"}]'
    parts = detect_multipart_messages(text)
    assert len(parts) == 2

    assert parts[0].context_type == ContextPartType.SYSTEM_PROMPT
    assert parts[0].title == "System Prompt"
    assert "You are helpful." in parts[0].content

    assert parts[1].context_type == ContextPartType.USER_MESSAGE
    assert parts[1].title == "User Message #2"
    assert "Hi!" in parts[1].content


def test_detect_multipart_with_tool_result():
    text = '[{"role": "tool", "content": "42"}]'
    parts = detect_multipart_messages(text)
    assert len(parts) == 1
    assert parts[0].context_type == ContextPartType.TOOL_RESULT


def test_detect_multipart_with_complex_content():
    """Message with list content should be serialized properly."""
    text = json.dumps([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is this?"},
                {"type": "image", "source": {"media_type": "image/png"}},
            ],
        }
    ])
    parts = detect_multipart_messages(text)
    assert len(parts) == 1
    assert parts[0].context_type == ContextPartType.USER_MESSAGE
    # Content should be stringified, not a list.
    assert isinstance(parts[0].content, str)
    assert "What is this?" in parts[0].content


def test_detect_multipart_metadata_computed():
    text = json.dumps([{"role": "system", "content": "A" * 100}])
    parts = detect_multipart_messages(text)
    assert len(parts) == 1
    assert parts[0].content_bytes > 0
    assert parts[0].token_hint > 0


def test_detect_multipart_invalid_json():
    """Invalid JSON should return empty list."""
    parts = detect_multipart_messages('[{"role": "system", invalid}]')
    assert parts == []


def test_detect_multipart_non_message_array():
    """Array without role field should return empty."""
    parts = detect_multipart_messages('[1, 2, 3]')
    assert parts == []


def test_detect_multipart_empty_array():
    parts = detect_multipart_messages('[]')
    assert parts == []
