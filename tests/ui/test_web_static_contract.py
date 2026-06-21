"""Web 静态契约：agents-cell 布局纪律（P-20 / T026）。
确保：
1. projects.css 中的 `.agents-cell` 不定义 `display: flex`
   （<td> 上的 flex 会破坏与相邻单元格一致的 border-height）。
2. HTML 模板中的 agents-cell 包含一个包装元素
   （如 `agents-cell__inner`）用于布局隔离。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_CSS = ROOT / 'src' / 'session_browser' / 'web' / 'static' / 'css' / 'projects.css'
PROJECTS_HTML = ROOT / 'src' / 'session_browser' / 'web' / 'templates' / 'projects.html'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


# ── 契约 1：.agents-cell 不得定义 display:flex ─────────────────────────


@pytest.mark.contract_case('UI-VISUAL-001')
def test_agents_cell_no_display_flex_in_css():
    """.agents-cell 规则块内不得包含 display: flex / display:flex。"""
    css = _read(PROJECTS_CSS)
    # 提取 .agents-cell 规则块（从选择器到下一个选择器或 EOF）
    import re

    match = re.search(r'\.agents-cell\s*\{([^}]*)\}', css)
    assert match, '.agents-cell selector not found in projects.css'

    block = match.group(1)
    # 检查任何形式的 display:flex（含/不含空格）
    has_flex = re.search(r'display\s*:\s*flex', block, re.IGNORECASE)
    assert not has_flex, (
        f'.agents-cell rule block contains display:flex, which breaks '
        f"border-height alignment with adjacent cells. Found: '{has_flex.group(0)}'"
    )


# ── 契约 2：agents-cell 内部必须有 wrapper ────────────────────────────


@pytest.mark.contract_case('UI-VISUAL-001')
def test_agents_cell_has_inner_wrapper_in_html():
    """agents-cell 内部必须包含 wrapper 元素（如 agents-cell__inner）。"""
    html = _read(PROJECTS_HTML)
    # 查找包含 inner wrapper 的 agents-cell td
    import re

    # 匹配 <td class="agents-cell"> ... </td>
    td_match = re.search(r'<td\s+class="agents-cell">(.*?)</td>', html, re.DOTALL)
    assert td_match, 'No <td class="agents-cell"> found in projects.html'

    td_content = td_match.group(1)
    # 检查是否有任何 agents-cell 相关的 inner wrapper 元素
    has_wrapper = re.search(r'class="agents-cell__\w+"', td_content)
    assert has_wrapper, (
        'agents-cell <td> lacks an inner wrapper element (e.g. agents-cell__inner). '
        'Wrap the badge macros inside a <div> or <span> with a dedicated class.'
    )


@pytest.mark.contract_case('UI-VISUAL-001')
def test_agents_cell_inner_class_named_consistently():
    """agents-cell 的 wrapper 类名应遵循 BEM 约定（agents-cell__inner 或类似）。"""
    html = _read(PROJECTS_HTML)
    import re

    td_match = re.search(r'<td\s+class="agents-cell">(.*?)</td>', html, re.DOTALL)
    if not td_match:
        return  # 上一个测试已覆盖

    td_content = td_match.group(1)
    has_inner = re.search(r'agents-cell__inner', td_content)
    assert has_inner, 'agents-cell wrapper should use BEM naming: agents-cell__inner'
