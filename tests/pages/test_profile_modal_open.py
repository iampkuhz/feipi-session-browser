"""验证 Payload 模态框和 Trace 结构的测试。

架构：
- 基于组件的 Jinja2 宏（sdp、sdt）替代内联 HTML。
- 工具调用通过 session_detail_timeline.html 中的 sdt.tool_batch 宏渲染。
- Payload 模态框在 base.html 中统一处理所有 payload 查看。
"""

import glob as _glob
from pathlib import Path

import pytest

TEMPLATE_DIR = Path(__file__).parents[2] / 'src' / 'session_browser' / 'web' / 'templates'
TIMELINE_PATH = TEMPLATE_DIR / 'components' / 'session_detail_timeline.html'
TIMELINE_DIR = TEMPLATE_DIR / 'components' / 'session_detail_timeline'


def _session_source():
    return (TEMPLATE_DIR / 'session.html').read_text(encoding='utf-8')


def _base_source():
    return (TEMPLATE_DIR / 'base.html').read_text(encoding='utf-8')


def _read_timeline_with_splits() -> str:
    """Read timeline wrapper + all split sub-components."""
    parts = [TIMELINE_PATH.read_text(encoding='utf-8')]
    for fp in sorted(_glob.glob(str(TIMELINE_DIR / '*.html'))):
        parts.append(Path(fp).read_text(encoding='utf-8'))
    return '\n'.join(parts)


def _timeline_component():
    return _read_timeline_with_splits()


# ── 工具渲染（组件宏） ──────────────────────────


@pytest.mark.contract_case('UI-INTERACTION-006')
def test_has_tool_batch_macro():
    """Timeline 组件必须定义 tool_batch 宏。"""
    source = _timeline_component()
    assert 'macro tool_batch' in source, 'tool_batch 宏必须存在'


@pytest.mark.contract_case('UI-INTERACTION-006')
def test_tool_rows_have_data_attrs():
    """工具行必须有用于识别的 data 属性。"""
    source = _timeline_component()
    assert 'data-tool-call-id' in source, '工具行必须有 data-tool-call-id'


@pytest.mark.contract_case('UI-INTERACTION-006')
def test_tool_rows_show_status():
    """工具行必须渲染状态信息。"""
    source = _timeline_component()
    assert 'tool.result_summary' in source or 'tool.status_tone' in source, '工具行必须显示状态'


# ── Payload 模态框（base.html） ────────────────────────────────────


@pytest.mark.contract_case('UI-INTERACTION-006')
def test_payload_modal_in_base():
    """Payload 模态框必须在 base.html 中定义。"""
    source = _base_source()
    assert 'payload-modal' in source, 'payload-modal 必须存在于 base.html 中'


# ── 组件使用 ────────────────────────────────────────────


@pytest.mark.contract_case('UI-INTERACTION-006')
def test_session_uses_sdt_macros():
    """session.html 必须使用 sdt 宏。"""
    source = _session_source()
    assert 'sdt.hero' in source, '应使用 sdt.hero 宏'
    assert 'sdt.trace_header' in source, '应使用 sdt.trace_header 宏'
    assert 'sdt.trace_round' in source, '应使用 sdt.trace_round 宏'


@pytest.mark.contract_case('UI-INTERACTION-006')
def test_session_uses_sdp_import():
    """session.html 必须导入 sdp 原语。"""
    source = _session_source()
    assert 'import' in source and 'sdp' in source, '应导入 sdp 原语'
