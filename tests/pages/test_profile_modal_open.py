"""验证 Payload 模态框和 Trace 结构的测试。

架构：
- 基于组件的 Jinja2 宏（sdp、sdt）替代内联 HTML。
- 工具调用通过 session_detail_timeline.html 中的 sdt.tool_batch 宏渲染。
- Payload 模态框在 base.html 中统一处理所有 payload 查看。
- 点击委托通过 view-switching.js 中的 _arpClosest 辅助函数处理（从 base.html 中提取）。
"""

import pytest

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
VIEW_SWITCHING_JS = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "static" / "js" / "view-switching.js"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _base_source():
    return (TEMPLATE_DIR / "base.html").read_text(encoding="utf-8")


def _view_switching_source():
    return (VIEW_SWITCHING_JS).read_text(encoding="utf-8")


def _timeline_component():
    return (TEMPLATE_DIR / "components" / "session_detail_timeline.html").read_text(encoding="utf-8")


# ── 工具渲染（组件宏） ──────────────────────────


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_has_tool_batch_macro():
    """Timeline 组件必须定义 tool_batch 宏。"""
    source = _timeline_component()
    assert "macro tool_batch" in source, "tool_batch 宏必须存在"


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_tool_rows_have_data_attrs():
    """工具行必须有用于识别的 data 属性。"""
    source = _timeline_component()
    assert "data-tool-call-id" in source, "工具行必须有 data-tool-call-id"


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_tool_rows_show_status():
    """工具行必须渲染状态信息。"""
    source = _timeline_component()
    assert "tool.result_summary" in source or "tool.status_tone" in source, (
        "工具行必须显示状态"
    )


# ── Payload 模态框（base.html） ────────────────────────────────────


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_payload_modal_in_base():
    """Payload 模态框必须在 base.html 中定义。"""
    source = _base_source()
    assert "payload-modal" in source, "payload-modal 必须存在于 base.html 中"


# ── 事件处理（base.html） ───────────────────────────────────


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_capture_phase_click_listener():
    """view-switching.js 必须有一个捕获阶段的点击监听器用于 [data-content-modal]。"""
    source = _view_switching_source()
    assert "addEventListener('click'" in source, (
        "view-switching.js 必须添加点击事件监听器"
    )
    assert ", true)" in source, (
        "view-switching.js 必须注册捕获阶段的点击监听器"
    )


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_closest_polyfill():
    """view-switching.js 必须定义 closest 辅助函数以兼容旧版 WebView。"""
    source = _view_switching_source()
    assert "_arpClosest" in source, (
        "view-switching.js 必须定义 _arpClosest 辅助函数"
    )
    assert "webkitMatchesSelector" in source, (
        "view-switching.js 的 _arpClosest 必须支持 webkitMatchesSelector"
    )


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_capture_handler_sets_handled_flag():
    """捕获阶段处理器必须设置 e.__contentModalHandled。"""
    source = _view_switching_source()
    assert "__contentModalHandled" in source, (
        "捕获处理器必须设置 e.__contentModalHandled 标志"
    )


# ── 组件使用 ────────────────────────────────────────────


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_session_uses_sdt_macros():
    """session.html 必须使用 sdt 宏。"""
    source = _session_source()
    assert "sdt.hero" in source, "应使用 sdt.hero 宏"
    assert "sdt.trace_header" in source, "应使用 sdt.trace_header 宏"
    assert "sdt.trace_round" in source, "应使用 sdt.trace_round 宏"


@pytest.mark.contract_case("UI-INTERACTION-006")
def test_session_uses_sdp_import():
    """session.html 必须导入 sdp 原语。"""
    source = _session_source()
    assert "import" in source and "sdp" in source, "应导入 sdp 原语"
