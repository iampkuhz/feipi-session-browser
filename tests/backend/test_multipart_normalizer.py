"""normalize_message_content 单元测试.

覆盖范围:
- 空值 / None 输入返回单个空文本部件.
- 纯空白输入.
- 简单 markdown 文本.
- 带多种语言的围栏代码块.
- JSON 对象和数组(独立和嵌入).
- 混合内容(markdown + 代码 + JSON).
- 一条消息中的多个代码块.
- 未闭合/部分围栏(回退到 markdown).
- 幂等性:运行两次得到相同结果.
- 内容保留:不丢失任何原始文本.
"""

import json

import pytest

from session_browser.domain.content_part import (
    ContentPart,
    ContentPartType,
    ContextPartType,
)
from session_browser.domain.normalizer import (
    detect_multipart_messages,
    normalize_context_parts,
    normalize_message_content,
)

EXPECTED_PAIR_COUNT = 2
MIN_COMPLEX_MIXED_PARTS = 4

# ─── 空值 / None 输入 ───────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_none_input() -> None:
    """保护 None 消息内容归一化为空 TEXT 部件的兼容契约."""
    parts = normalize_message_content(None)
    assert isinstance(parts, list)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT
    assert parts[0].content == ''


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_empty_string() -> None:
    """保护空字符串消息归一化为空 TEXT 部件且不产生额外片段."""
    parts = normalize_message_content('')
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT
    assert parts[0].content == ''


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_whitespace_only() -> None:
    """保护纯空白输入只保留为单个文本部件而不误判为结构化内容."""
    parts = normalize_message_content('   \n\n  \t  ')
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT


# ─── 简单 markdown ─────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_simple_markdown() -> None:
    """保护标题、强调和列表组成的普通 markdown 被整体识别为 MARKDOWN."""
    text = '# Hello\n\nThis is **bold** text.\n\n- Item 1\n- Item 2'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.MARKDOWN
    assert '# Hello' in parts[0].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_markdown_with_table() -> None:
    """保护 markdown 表格语法不会被 multipart 归一化拆成非 markdown 片段."""
    text = '| A | B |\n|---|---|\n| 1 | 2 |'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.MARKDOWN


# ─── 围栏代码块 ──────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_python_code_block() -> None:
    """保护 python 围栏代码块识别为 CODE 并提取语言和代码正文."""
    text = "```python\ndef hello():\n    print('world')\n```"
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == 'python'
    assert 'def hello():' in parts[0].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_typescript_code_block() -> None:
    """保护 typescript 围栏代码块识别为 CODE 并保留语言标签."""
    text = '```typescript\nconst x: number = 1;\n```'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == 'typescript'


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_code_block_no_language() -> None:
    """保护无语言围栏代码块识别为 CODE 且语言字段保持空字符串."""
    text = '```\nsome code here\n```'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == ''
    assert 'some code here' in parts[0].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_tilde_fence() -> None:
    """保护波浪线围栏代码块与反引号围栏具备相同识别语义."""
    text = '~~~bash\necho hello\n~~~'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == 'bash'


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_multiple_code_blocks() -> None:
    """保护同一消息内多个代码围栏按顺序拆分并保留 markdown 间隔."""
    text = (
        'Here is some Python:\n\n'
        '```python\ndef foo(): pass\n```\n\n'
        'And here is some JS:\n\n'
        "```javascript\nconsole.log('hi');\n```"
    )
    parts = normalize_message_content(text)
    code_parts = [p for p in parts if p.part_type == ContentPartType.CODE]
    md_parts = [p for p in parts if p.part_type == ContentPartType.MARKDOWN]
    assert len(code_parts) == EXPECTED_PAIR_COUNT
    assert code_parts[0].language == 'python'
    assert code_parts[1].language == 'javascript'
    assert len(md_parts) >= 1


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_unclosed_fence_with_language() -> None:
    """保护未闭合且带语言的围栏仍按代码模式识别并提取语言."""
    text = '```python\ndef broken():'
    parts = normalize_message_content(text)
    # 因内容以 ``` 开头且具有代码模式,被检测为代码.
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    # 语言从围栏首行提取.
    assert parts[0].language == 'python'
    assert 'def broken():' in parts[0].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_unclosed_fence_prose() -> None:
    """保护未闭合围栏即使包含散文也遵循围栏优先的 CODE 识别契约."""
    text = '```\nThis is just plain text, not code.\nNo functions or classes here.'
    parts = normalize_message_content(text)
    # 因内容以 ``` 开头(围栏代码模式),被检测为代码.
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE


# ─── JSON ────────────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_standalone_json_object() -> None:
    """保护独立 JSON 对象被归一化为单个 JSON 部件并保留键名内容."""
    text = '{"status": "ok", "count": 5}'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON
    assert '"status"' in parts[0].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_standalone_json_array() -> None:
    """保护独立 JSON 数组被归一化为单个 JSON 部件."""
    text = '[1, 2, {"name": "test"}]'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_nested_json() -> None:
    """保护嵌套对象和数组组成的 JSON 不被错误拆分或降级."""
    text = '{"a": {"b": [1, 2, 3], "c": {"d": "e"}}}'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_json_with_whitespace() -> None:
    """保护首尾空白包裹的 JSON 仍可按 JSON 部件识别."""
    text = '\n  {"key": "value"}\n'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.JSON


# ─── 混合内容 ───────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_markdown_then_code() -> None:
    """保护 markdown 引言后接代码围栏时拆分出 MARKDOWN 和 CODE."""
    text = "Here's the function:\n\n```python\ndef hello():\n    pass\n```"
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.MARKDOWN in types
    assert ContentPartType.CODE in types


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_code_then_markdown() -> None:
    """保护代码围栏后接说明文本时拆分出 CODE 和 MARKDOWN."""
    text = '```python\nx = 1\n```\n\nThis sets x to 1.'
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.CODE in types
    assert ContentPartType.MARKDOWN in types


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_json_embedded_in_markdown() -> None:
    """保护被空行包围的嵌入 JSON 可从周围 markdown 中分离."""
    text = (
        'The API returned this response:\n\n'
        '{"status": "ok", "data": [1, 2, 3]}\n\n'
        'Which means everything is fine.'
    )
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.JSON in types
    assert ContentPartType.MARKDOWN in types


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_complex_mixed() -> None:
    """保护 markdown、代码、JSON 混排消息按语义拆成多个有序部件."""
    text = (
        'Let me show you the config:\n\n'
        '```yaml\nname: test\nversion: 1\n```\n\n'
        'The response was:\n\n'
        '{"result": "success"}\n\n'
        "That's all."
    )
    parts = normalize_message_content(text)
    types = [p.part_type for p in parts]
    assert ContentPartType.CODE in types
    assert ContentPartType.JSON in types
    assert ContentPartType.MARKDOWN in types
    # 应至少有 4 个部分(md + code + md + json + md)
    assert len(parts) >= MIN_COMPLEX_MIXED_PARTS


# ─── 内容保留 ────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_no_content_lost_simple() -> None:
    """保护 markdown 与代码混合归一化后不丢失任一原始文本片段."""
    text = 'Hello world\n\n```python\nx = 1\n```\n\nDone.'
    parts = normalize_message_content(text)
    all_content = ' '.join(p.content for p in parts)
    assert 'Hello world' in all_content
    assert 'x = 1' in all_content
    assert 'Done.' in all_content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_no_content_lost_json() -> None:
    """保护嵌入 JSON 的混合文本归一化后保留引言、键值和收尾内容."""
    text = 'Intro\n\n{"key": "value"}\n\nOutro'
    parts = normalize_message_content(text)
    all_content = ' '.join(p.content for p in parts)
    assert 'Intro' in all_content
    assert '"key"' in all_content
    assert '"value"' in all_content
    assert 'Outro' in all_content


# ─── 幂等性 ──────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_idempotent_markdown() -> None:
    """保护 markdown 部件内容再次归一化时保持片段数量和类型稳定."""
    text = '# Hello\n\nWorld'
    parts1 = normalize_message_content(text)
    # 再次归一化合并后的内容
    combined = parts1[0].content
    parts2 = normalize_message_content(combined)
    assert len(parts1) == len(parts2)
    assert parts1[0].part_type == parts2[0].part_type


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_idempotent_code() -> None:
    """保护无围栏代码内容再次归一化时仍可通过代码模式识别为 CODE."""
    code = 'def foo():\n    pass'
    part = ContentPart(
        part_type=ContentPartType.CODE,
        content=code,
        language='python',
    )
    parts = normalize_message_content(part.content)
    # 无围栏的代码应通过内容模式检测为代码.
    code_parts = [p for p in parts if p.part_type == ContentPartType.CODE]
    assert len(code_parts) >= 1


# ─── 边界情况 ──────────────────────────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_json_array_at_start() -> None:
    """保护消息开头的 JSON 数组优先识别为 JSON 而非 markdown."""
    text = '[{"id": 1}]\n\nHere is an explanation.'
    parts = normalize_message_content(text)
    assert parts[0].part_type == ContentPartType.JSON


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_code_block_with_json_inside() -> None:
    """保护代码围栏中的 JSON 内容归属 CODE 而不被拆成独立 JSON."""
    text = '```json\n{"key": "value"}\n```'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == 'json'


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_empty_lines_between_code_blocks() -> None:
    """保护多个代码围栏之间的连续空行不影响代码片段计数."""
    text = '```python\na = 1\n```\n\n\n```python\nb = 2\n```'
    parts = normalize_message_content(text)
    code_parts = [p for p in parts if p.part_type == ContentPartType.CODE]
    assert len(code_parts) == EXPECTED_PAIR_COUNT


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_single_line_code() -> None:
    """保护单反引号 inline code 不触发围栏代码识别并保留为 MARKDOWN."""
    text = '`inline code`'
    parts = normalize_message_content(text)
    # 单反引号不是围栏,应为 markdown
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.MARKDOWN


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_long_fence() -> None:
    """保护超过三个反引号的长围栏仍识别为 CODE 并提取语言."""
    text = '````python\ncode here\n````'
    parts = normalize_message_content(text)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.CODE
    assert parts[0].language == 'python'


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_invalid_json_fallback() -> None:
    """保护形似 JSON 但解析失败的内容回退为 markdown 非 JSON."""
    text = '{"key": }'
    parts = normalize_message_content(text)
    # 无效 JSON 应回退为 markdown.
    assert all(p.part_type != ContentPartType.JSON for p in parts)


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_output_is_list_of_contentpart() -> None:
    """保护 normalize_message_content 始终返回 ContentPart 实例列表."""
    parts = normalize_message_content('test content')
    assert isinstance(parts, list)
    for p in parts:
        assert isinstance(p, ContentPart)


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_content_part_has_no_empty_metadata() -> None:
    """保护输出 ContentPart 的 metadata、language 和 filename 默认字段可用."""
    parts = normalize_message_content('test')
    for p in parts:
        assert isinstance(p.metadata, dict)
        assert isinstance(p.language, str)
        assert isinstance(p.filename, str)


# ─── I-08 normalize_context_parts ──────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_normalize_context_parts_none() -> None:
    """保护 None 上下文归一化为空 TEXT 并计算零字节内容."""
    parts = normalize_context_parts(None)
    assert len(parts) == 1
    assert parts[0].part_type == ContentPartType.TEXT
    assert parts[0].content == ''
    assert parts[0].content_bytes == 0


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_normalize_context_parts_empty() -> None:
    """保护空上下文归一化为 UNKNOWN 类型的单个上下文部件."""
    parts = normalize_context_parts('')
    assert len(parts) == 1
    assert parts[0].context_type == ContextPartType.UNKNOWN


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_normalize_context_parts_sets_type_and_title() -> None:
    """保护默认上下文类型和标题会传播到所有归一化部件并计算元数据."""
    parts = normalize_context_parts(
        'Hello world',
        default_context_type=ContextPartType.USER_MESSAGE,
        title='User Message #1',
    )
    assert len(parts) >= 1
    for p in parts:
        assert p.context_type == ContextPartType.USER_MESSAGE
        assert p.title == 'User Message #1'
        # 元数据应自动计算
        assert p.content_bytes > 0 or p.content == ''
        assert p.token_hint >= 0


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_normalize_context_parts_markdown_with_code() -> None:
    """保护上下文归一化在 markdown 加代码混排时保留类型、标题和拆分语义."""
    text = 'Here is code:\n\n```python\nx = 1\n```\n\nDone.'
    parts = normalize_context_parts(
        text,
        default_context_type=ContextPartType.ASSISTANT_MESSAGE,
        title='Assistant #1',
    )
    # 应至少有 2 个部分(markdown 引言 + 代码).
    assert len(parts) >= EXPECTED_PAIR_COUNT
    types = [p.part_type for p in parts]
    assert ContentPartType.CODE in types
    assert ContentPartType.MARKDOWN in types
    # 所有部分应具有相同的 context_type 和 title.
    for p in parts:
        assert p.context_type == ContextPartType.ASSISTANT_MESSAGE
        assert p.title == 'Assistant #1'


# ─── I-08 detect_multipart_messages ────────────────────────────────────


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_not_json() -> None:
    """保护非 JSON 纯文本不会被误判为 multipart 消息数组."""
    result = detect_multipart_messages('Hello world')
    assert result == []


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_empty() -> None:
    """保护空内容和纯空白内容检测 multipart 时返回空列表."""
    assert detect_multipart_messages('') == []
    assert detect_multipart_messages('   ') == []


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_valid_messages_array() -> None:
    """保护 role 消息数组映射为对应上下文类型、标题和内容."""
    text = '[{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "Hi!"}]'
    parts = detect_multipart_messages(text)
    assert len(parts) == EXPECTED_PAIR_COUNT

    assert parts[0].context_type == ContextPartType.SYSTEM_PROMPT
    assert parts[0].title == 'System Prompt'
    assert 'You are helpful.' in parts[0].content

    assert parts[1].context_type == ContextPartType.USER_MESSAGE
    assert parts[1].title == 'User Message #2'
    assert 'Hi!' in parts[1].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_with_tool_result() -> None:
    """保护 tool role 消息被识别为 TOOL_RESULT 上下文部件."""
    text = '[{"role": "tool", "content": "42"}]'
    parts = detect_multipart_messages(text)
    assert len(parts) == 1
    assert parts[0].context_type == ContextPartType.TOOL_RESULT


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_with_complex_content() -> None:
    """保护列表型复杂 content 会字符串化并保留可检索文本."""
    text = json.dumps(
        [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'What is this?'},
                    {'type': 'image', 'source': {'media_type': 'image/png'}},
                ],
            }
        ]
    )
    parts = detect_multipart_messages(text)
    assert len(parts) == 1
    assert parts[0].context_type == ContextPartType.USER_MESSAGE
    # 内容应为字符串化形式,而非列表.
    assert isinstance(parts[0].content, str)
    assert 'What is this?' in parts[0].content


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_metadata_computed() -> None:
    """保护 multipart 消息检测结果会计算 content_bytes 和 token_hint."""
    text = json.dumps([{'role': 'system', 'content': 'A' * 100}])
    parts = detect_multipart_messages(text)
    assert len(parts) == 1
    assert parts[0].content_bytes > 0
    assert parts[0].token_hint > 0


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_invalid_json() -> None:
    """保护无效 JSON 输入检测 multipart 时安全返回空列表."""
    parts = detect_multipart_messages('[{"role": "system", invalid}]')
    assert parts == []


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_non_message_array() -> None:
    """保护不含 role 的 JSON 数组不会被当作消息数组."""
    parts = detect_multipart_messages('[1, 2, 3]')
    assert parts == []


@pytest.mark.contract_case('DATA-SOURCE-001')
def test_detect_multipart_empty_array() -> None:
    """保护空 JSON 数组检测 multipart 时返回空列表."""
    parts = detect_multipart_messages('[]')
    assert parts == []
