"""ContentPart 检测函数单元测试.

覆盖范围:
- is_json 检测有效 JSON 对象和数组
- is_image_url 检测 HTTP URL,data URI,Markdown 图片语法
- is_html 检测 HTML 文档但不检测散文中的内联标签
- is_code_block 检测围栏代码,文件扩展名,代码模式
- detect_content_type 对常见负载返回正确类型
- 空值/None 处理
"""

import pytest

from session_browser.domain.content_part import (
    ContentPart,
    ContentPartType,
    ContextPartType,
    detect_content_type,
    is_code_block,
    is_html,
    is_image_url,
    is_json,
)
from session_browser.domain.serializers import content_part_from_dict, content_part_to_dict

EXISTING_CONTENT_BYTES = 100
EXISTING_TOKEN_HINT = 25
SERIALIZED_CONTENT_BYTES = 4

# ─── is_json ──────────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_object() -> None:
    """Protects object JSON detection in content-type normalization."""
    assert is_json('{"key": "value"}') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_array() -> None:
    """Protects array JSON detection in content-type normalization."""
    assert is_json('[1, 2, 3]') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_nested() -> None:
    """Protects nested JSON detection used before content part typing."""
    assert is_json('{"a": {"b": [1, 2]}}') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_with_leading_whitespace() -> None:
    """Protects JSON detection after leading whitespace trimming."""
    assert is_json('  {"key": "value"}') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_invalid() -> None:
    """Protects invalid JSON rejection before specialized content typing."""
    assert is_json('{"key": }') is False
    assert is_json('[1, 2,]') is False
    assert is_json('not json') is False
    assert is_json('') is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_markdown_not_json() -> None:
    """Protects markdown prose from being misclassified as JSON."""
    assert is_json('# Hello\n\nThis is text.') is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_json_ordered_list_not_json() -> None:
    """Protects ordered-list markdown from JSON misclassification."""
    assert is_json('1. First\n2. Second') is False


# ─── is_image_url ─────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_url_png() -> None:
    """Protects PNG URL detection for image content parts."""
    assert is_image_url('https://example.com/diagram.png') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_url_jpg() -> None:
    """Protects JPG URL detection for image content parts."""
    assert is_image_url('https://example.com/photo.jpg') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_url_gif() -> None:
    """Protects GIF URL detection for image content parts."""
    assert is_image_url('https://example.com/anim.gif') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_url_webp() -> None:
    """Protects WebP URL detection for image content parts."""
    assert is_image_url('https://example.com/image.webp') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_url_with_query_params() -> None:
    """Protects image URL detection when signed query parameters are present."""
    assert is_image_url('https://example.com/img.png?token=abc') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_data_uri() -> None:
    """Protects data URI image detection for inline image payloads."""
    assert is_image_url('data:image/png;base64,iVBORw0KGgo') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_markdown_syntax() -> None:
    """Protects Markdown image syntax detection for rendered content parts."""
    assert is_image_url('![alt text](https://example.com/img.png)') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_image_url_negative() -> None:
    """Protects non-image URLs and prose from image classification."""
    assert is_image_url('https://example.com/page.html') is False
    assert is_image_url('https://example.com/data.json') is False
    assert is_image_url('') is False
    assert is_image_url('just some text') is False


# ─── is_html ──────────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_full_document() -> None:
    """Protects full HTML document detection for HTML content parts."""
    assert is_html('<!DOCTYPE html>\n<html><body>Hello</body></html>') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_table() -> None:
    """Protects standalone table markup detection as HTML content."""
    assert is_html('<table><tr><td>Cell</td></tr></table>') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_comment() -> None:
    """Protects commented HTML fragments from being treated as plain text."""
    assert is_html('<!-- This is a comment -->\n<div>Content</div>') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_with_whitespace() -> None:
    """Protects HTML detection after leading whitespace trimming."""
    assert is_html('  \n<div class="container">Hello</div>') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_inline_tag_in_prose_not_detected() -> None:
    """Protects prose with inline tags from HTML document classification."""
    assert is_html('Use <code> for inline code.') is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_empty() -> None:
    """Protects empty content from HTML classification."""
    assert is_html('') is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_html_plain_text() -> None:
    """Protects Markdown prose from HTML classification."""
    assert is_html('# Heading\n\nSome markdown text.') is False


# ─── is_code_block ────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_fenced() -> None:
    """Protects fenced code block detection for code content parts."""
    assert is_code_block('```python\ndef hello():\n    pass\n```') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_python_def() -> None:
    """Protects Python function snippets as code content."""
    assert is_code_block('def hello():\n    print("world")') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_python_class() -> None:
    """Protects Python class snippets as code content."""
    assert is_code_block('class MyClass:\n    pass') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_python_import() -> None:
    """Protects Python import snippets as code content."""
    assert is_code_block('from os import path') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_typescript() -> None:
    """Protects TypeScript snippets as code content."""
    assert is_code_block('const x = 1;\nexport default x;') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_go() -> None:
    """Protects Go snippets as code content."""
    assert is_code_block('package main\n\nfunc main() {}') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_rust() -> None:
    """Protects Rust snippets as code content."""
    assert is_code_block('pub fn main() {\n    println!("hello");\n}') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_with_filename() -> None:
    """Protects filename hints that promote plain text snippets to code."""
    assert is_code_block('x = 1\nprint(x)', filename_hint='script.py') is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_markdown_file_not_code() -> None:
    """Protects Markdown filename hints from false code classification."""
    assert is_code_block('# README\n\nSome docs.', filename_hint='README.md') is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_prose_not_code() -> None:
    """Protects plain prose from code classification."""
    assert is_code_block('Hello world, this is a normal paragraph.') is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_is_code_empty() -> None:
    """Protects empty content from code classification."""
    assert is_code_block('') is False


# ─── detect_content_type ──────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_empty() -> None:
    """Protects empty content defaulting to text content type."""
    assert detect_content_type('') == ContentPartType.TEXT
    assert detect_content_type('   \n\n  ') == ContentPartType.TEXT


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_markdown() -> None:
    """Protects Markdown payload classification in content detection."""
    result = detect_content_type('# Hello\n\nThis is **bold** text.')
    assert result == ContentPartType.MARKDOWN


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_json() -> None:
    """Protects JSON payload classification in content detection."""
    result = detect_content_type('{"status": "ok", "count": 5}')
    assert result == ContentPartType.JSON


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_image() -> None:
    """Protects image payload classification in content detection."""
    result = detect_content_type('https://example.com/diagram.png')
    assert result == ContentPartType.IMAGE


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_code() -> None:
    """Protects code snippet classification in content detection."""
    result = detect_content_type('def hello():\n    print("world")')
    assert result == ContentPartType.CODE


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_code_with_filename() -> None:
    """Protects filename-based code classification in content detection."""
    result = detect_content_type('x = 1', filename_hint='main.py')
    assert result == ContentPartType.CODE


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_html() -> None:
    """Protects HTML fragment classification in content detection."""
    result = detect_content_type('<table><tr><td>Cell</td></tr></table>')
    assert result == ContentPartType.HTML


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_ordered_list_not_code() -> None:
    """Protects ordered-list Markdown from code classification."""
    result = detect_content_type('1. First step\n2. Second step\n3. Third step')
    assert result == ContentPartType.MARKDOWN


# ─── ContentPart 模型 ────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_properties() -> None:
    """Protects ContentPart boolean helpers for renderer branching."""
    part = ContentPart(part_type=ContentPartType.CODE, content='x=1', language='python')
    assert part.is_code is True
    assert part.is_text is False
    assert part.is_markdown is False
    assert part.is_json is False
    assert part.is_image is False
    assert part.is_html is False


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_serialization() -> None:
    """Protects ContentPart serializer round-trip fields."""
    part = ContentPart(
        part_type=ContentPartType.CODE,
        content='print(1)',
        language='python',
        filename='test.py',
        metadata={'line_count': 1},
    )
    d = content_part_to_dict(part)
    assert d['part_type'] == 'code'
    assert d['language'] == 'python'
    assert d['filename'] == 'test.py'
    assert d['metadata']['line_count'] == 1

    restored = content_part_from_dict(d)
    assert restored.part_type == part.part_type
    assert restored.content == part.content
    assert restored.language == part.language
    assert restored.filename == part.filename


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_type_constants() -> None:
    """Protects public ContentPartType string constants used in payload contracts."""
    assert ContentPartType.TEXT == 'text'
    assert ContentPartType.MARKDOWN == 'markdown'
    assert ContentPartType.JSON == 'json'
    assert ContentPartType.IMAGE == 'image'
    assert ContentPartType.CODE == 'code'
    assert ContentPartType.HTML == 'html'


# ─── I-08 ContextPartType constants ────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_context_part_type_constants() -> None:
    """Protects public ContextPartType constants used in context attribution."""
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


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_new_fields_defaults() -> None:
    """Protects default context fields for newly built content parts."""
    part = ContentPart(part_type='text', content='hello')

    assert part.context_type == ContextPartType.UNKNOWN
    assert part.title == ''
    assert part.content_bytes == 0
    assert part.token_hint == 0


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_new_fields_set() -> None:
    """Protects explicit context fields on content part construction."""
    part = ContentPart(
        part_type='markdown',
        content='Hello world',
        context_type='user_message',
        title='User Message #1',
    )
    assert part.context_type == 'user_message'
    assert part.title == 'User Message #1'


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_context_type_properties() -> None:
    """Protects context-type boolean helpers used by session detail views."""
    part = ContentPart(
        part_type='markdown', content='test', context_type=ContextPartType.SYSTEM_PROMPT
    )
    assert part.is_system_prompt is True
    assert part.is_user_message is False
    assert part.is_tool_result is False
    assert part.is_attachment is False

    part2 = ContentPart(part_type='text', content='test', context_type=ContextPartType.USER_MESSAGE)
    assert part2.is_user_message is True

    part3 = ContentPart(part_type='json', content='{}', context_type=ContextPartType.TOOL_RESULT)
    assert part3.is_tool_result is True


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_compute_metadata() -> None:
    """Protects byte and token metadata derivation for content parts."""
    part = ContentPart(part_type='markdown', content='Hello world, this is a test.')
    assert part.content_bytes == 0  # 尚未计算
    assert part.token_hint == 0

    part.compute_metadata()
    assert part.content_bytes > 0
    assert part.token_hint > 0
    # 31 字符 / 4 ≈ 7 tokens(启发式估算)
    assert part.token_hint == max(1, 31 // 4)


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_compute_metadata_preserves_existing() -> None:
    """Protects caller-provided metadata from being overwritten."""
    part = ContentPart(
        part_type='markdown',
        content='Hello',
        content_bytes=EXISTING_CONTENT_BYTES,
        token_hint=EXISTING_TOKEN_HINT,
    )
    part.compute_metadata()
    assert part.content_bytes == EXISTING_CONTENT_BYTES
    assert part.token_hint == EXISTING_TOKEN_HINT


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_compute_all() -> None:
    """Protects batch metadata computation for content part collections."""
    parts = [
        ContentPart(part_type='text', content='a'),
        ContentPart(part_type='markdown', content='Hello world'),
    ]
    ContentPart.compute_all(parts)
    for p in parts:
        assert p.content_bytes > 0 or p.content == ''
        assert p.token_hint >= 0


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_serialization_includes_new_fields() -> None:
    """Protects serializer output for context metadata fields."""
    part = ContentPart(
        part_type='markdown',
        content='test',
        context_type='user_message',
        title='User #1',
        content_bytes=SERIALIZED_CONTENT_BYTES,
        token_hint=1,
    )
    d = content_part_to_dict(part)
    assert d['context_type'] == 'user_message'
    assert d['title'] == 'User #1'
    assert d['content_bytes'] == SERIALIZED_CONTENT_BYTES
    assert d['token_hint'] == 1

    restored = content_part_from_dict(d)
    assert restored.context_type == part.context_type
    assert restored.title == part.title
    assert restored.content_bytes == part.content_bytes
    assert restored.token_hint == part.token_hint
