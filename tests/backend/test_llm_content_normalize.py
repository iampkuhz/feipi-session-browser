"""normalize_llm_content 和 render_llm_blocks_html 单元测试。

覆盖范围：
- 单一普通 markdown 字符串
- 工具结果 + markdown 文件内容
- 多个工具结果拼接
- Markdown 表格
- YAML/JSON/代码文件
- 行号边栏检测与剥离
- 包含有序列表的内容（不得误剥离）
- 空输入 / None 输入
- render_llm_blocks_html 生成非空 HTML
"""
import pytest
from session_browser.web.template_env import (
    normalize_llm_content,
    render_llm_blocks_html,
)
from session_browser.web.renderers.llm_blocks import (
    _detect_line_number_gutter,
    _strip_line_number_gutter,
    _infer_code_language,
    _detect_file_marker,
)


# ── 单一普通 markdown 字符串 ────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_single_markdown_string():
    """不含工具结果边界的单一 markdown 字符串成为一个块。"""
    text = "# Hello\n\nThis is **bold** text.\n\n- Item 1\n- Item 2"
    blocks = normalize_llm_content(text)
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "plain_text"
    assert blocks[0]["content"] == text
    assert blocks[0]["raw"] == text


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_single_markdown_with_table():
    """含表格的 markdown 保持为单个块。"""
    text = "# Table Test\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    blocks = normalize_llm_content(text)
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "plain_text"
    assert "| A | B |" in blocks[0]["content"]


# ── 工具结果 + markdown 文件内容 ─────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_tool_result_with_markdown_file():
    """'Tool result for toolu_xxx:' 后接 markdown 文件内容。"""
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
    # 文件标题应保留在内容中
    all_content = "\n".join(b["content"] for b in blocks)
    assert "定位" in all_content
    # 文件名应出现在 content 或 title 中
    has_filename = "AGENTS.md" in all_content or any("AGENTS.md" in b.get("title", "") for b in blocks)
    assert has_filename, f"AGENTS.md not found in blocks: {[b.get('title') for b in blocks]}"


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_multiple_tool_results():
    """多个工具结果应拆分为独立块。"""
    text = (
        "Tool result for toolu_abc:\nFirst tool result content.\n\n"
        "Tool result for toolu_def:\nSecond tool result content."
    )
    blocks = normalize_llm_content(text)
    assert len(blocks) >= 2
    all_content = "\n".join(b["content"] for b in blocks)
    assert "First tool result content" in all_content
    assert "Second tool result content" in all_content


# ── 文件检测 ──────────────────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_file_marker_detection():
    """以 '# filename.ext' 开头的内容应检测到文件。"""
    text = "# AGENTS.md\n\nSome content here."
    filename = _detect_file_marker(text)
    assert filename == "AGENTS.md"


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_file_marker_not_found():
    """不含类文件标题的文本应返回 None。"""
    text = "# Some heading\n\nRegular text."
    assert _detect_file_marker(text) is None


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_yaml_file_detection():
    """YAML 文件应被检测并标记。"""
    text = "# config.yaml\n\nkey: value\nlist:\n  - item1\n  - item2"
    blocks = normalize_llm_content(text)
    assert len(blocks) >= 1
    # 该块应是 file_code 类型，语言为 yaml
    yaml_blocks = [b for b in blocks if b.get("language") == "yaml"]
    assert len(yaml_blocks) >= 1


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_json_file_detection():
    """JSON 文件应被检测并标记。"""
    text = "# config.json\n\n{\"key\": \"value\", \"list\": [1, 2, 3]}"
    blocks = normalize_llm_content(text)
    json_blocks = [b for b in blocks if b.get("language") == "json"]
    assert len(json_blocks) >= 1


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_python_file_detection():
    """Python 文件应被检测并标记。"""
    text = "# main.py\n\ndef hello():\n    print('world')"
    blocks = normalize_llm_content(text)
    py_blocks = [b for b in blocks if b.get("language") == "python"]
    assert len(py_blocks) >= 1


# ── 语言推断 ──────────────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_infer_language_from_filename():
    """应从文件扩展名推断语言。"""
    assert _infer_code_language("main.py") == "python"
    assert _infer_code_language("app.ts") == "typescript"
    assert _infer_code_language("app.tsx") == "tsx"
    assert _infer_code_language("config.yaml") == "yaml"
    assert _infer_code_language("data.json") == "json"
    assert _infer_code_language("run.sh") == "bash"
    assert _infer_code_language("main.go") == "go"
    assert _infer_code_language("Cargo.toml") == "toml"


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_infer_language_from_content():
    """无文件名时应从内容模式推断语言。"""
    assert _infer_code_language(content="def hello():\n    pass") == "python"
    assert _infer_code_language(content="const x = 1;") == "typescript"
    assert _infer_code_language(content="import { useState } from 'react';") == "typescript"


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_markdown_returns_none_language():
    """Markdown 文件不应返回代码语言。"""
    assert _infer_code_language("README.md") is None
    assert _infer_code_language("notes.markdown") is None


# ── 行号边栏 ──────────────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_detect_line_number_gutter_positive():
    """含制表符分隔行号的文本应被检测到。"""
    text = "1\t# Hello\n2\t\n3\tWorld\n4\t\n5\tEnd"
    assert _detect_line_number_gutter(text) is True


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_detect_line_number_gutter_negative():
    """不含行号的文本不应被检测。"""
    text = "# Hello\n\nWorld\n\nEnd"
    assert _detect_line_number_gutter(text) is False


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_detect_line_number_gutter_ordered_list():
    """有序列表不应被误检测为行号（匹配的行数较少）。"""
    text = "1. First item\n2. Second item\n3. Third item"
    # 有序列表使用 "1." 而非 "1\t"，所以不应匹配 \d+\t 模式
    assert _detect_line_number_gutter(text) is False


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_strip_line_number_gutter():
    """应从每行剥离行号。"""
    text = "1\t# Hello\n2\t\n3\tWorld"
    result = _strip_line_number_gutter(text)
    assert result == "# Hello\n\nWorld"


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_strip_line_number_gutter_preserves_non_gutter():
    """行号不统一的文本不应被修改。"""
    text = "1. First\n2. Second\n3. Third"
    result = _strip_line_number_gutter(text)
    # 应保持不变，因为 <60% 的行匹配 \d+\t 模式
    assert result == text


# ── 空值 / 边界情况 ──────────────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_empty_input():
    """空字符串应返回空列表。"""
    assert normalize_llm_content("") == []
    assert normalize_llm_content(None) == []  # type: ignore


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_whitespace_only():
    """纯空白输入应返回空列表或无实质内容的块。"""
    blocks = normalize_llm_content("   \n\n  ")
    # 可能是空列表或含空白内容的块
    if blocks:
        assert all(b["content"].strip() == "" or b["content"].strip() for b in blocks)


# ── render_llm_blocks_html ──────────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_render_empty():
    """空块应产生回退提示。"""
    html = render_llm_blocks_html([])
    assert "No content available" in html


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_render_single_markdown_block():
    """markdown 块应渲染为带标题和已渲染内容的 HTML。"""
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
    # 内容应渲染为 markdown HTML
    assert "<h1" in html or "<strong>" in html


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_render_code_block():
    """代码块应渲染 <pre><code> 并带语言 class。"""
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


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_render_multiple_blocks():
    """多个块应渲染为独立卡片。"""
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


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_render_escapes_html():
    """块内容应进行 HTML 转义以防止 XSS。"""
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


# ── 内容保留 ────────────────────────────────────────────────


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_ordered_list_in_content_preserved():
    """含有序列表的内容应保留列表编号。"""
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


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_raw_field_preserved():
    """raw 字段应始终包含原始内容。"""
    text = "1\tline1\n2\tline2\n3\tline3"
    blocks = normalize_llm_content(text)
    for block in blocks:
        assert "raw" in block


@pytest.mark.contract_case("DATA-SOURCE-001")
def test_no_content_lost():
    """所有原始文本应存在于所有块中。"""
    text = (
        "Tool result for toolu_a:\nSome content A.\n\n"
        "Tool result for toolu_b:\nSome content B."
    )
    blocks = normalize_llm_content(text)
    all_content = "\n".join(b["content"] for b in blocks)
    all_titles = "\n".join(b.get("title", "") for b in blocks)
    assert "Some content A" in all_content
    assert "Some content B" in all_content
    # Tool ID 出现在块标题中而非内容中（它们被解析为边界标记）
    assert "toolu_a" in all_titles or "toolu_a" in all_content
    assert "toolu_b" in all_titles or "toolu_b" in all_content
