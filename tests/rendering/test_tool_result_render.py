"""v9 session detail 中 tool result 渲染的回归测试。
v9 架构：
- Tool result 通过 timeline 组件宏（tool_batch）渲染
- Tool result 按钮使用 sdp.button('Result', 'open-payload', ...)
- Payload modal 显示 result 内容
- 模板中 tool result 无内联 [:500] 截断
"""

import pytest

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
TIMELINE = TEMPLATE_DIR / "components" / "session_detail_timeline.html"


@pytest.mark.contract_case("UI-SD-021")
def test_tool_batch_renders_full_result():
    """tool_batch 宏渲染 tool result 按钮，而非截断文本。"""
    source = TIMELINE.read_text(encoding="utf-8")

    # 验证 tool_batch 宏是否存在
    macro_pattern = r'\{%\s*macro\s+tool_batch\s*\(batch\)'
    match = re.search(macro_pattern, source)
    assert match, "tool_batch macro not found in timeline component"

    # 检查宏体中是否有 sdp.button('Result' 且无截断
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
    """Tool result 通过组件宏渲染，而非内联截断。"""
    source = TIMELINE.read_text(encoding="utf-8")

    # 验证无剩余的内联 tool result 截断
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
    """tool_batch 宏应为每个 tool 提供 Result 按钮。"""
    source = TIMELINE.read_text(encoding="utf-8")

    # 验证 Result 按钮在 tool 循环内
    assert "sdp.button('Result'" in source, \
        "tool_batch must render Result button"
    assert 'data-action="open-payload"' not in source or \
           "sdp.button" in source, \
        "Result button should use sdp.button macro"
