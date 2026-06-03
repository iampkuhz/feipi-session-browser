"""会话详情追踪中 LLM 调用卡片契约测试。

通过 session_detail_timeline.html 中的 sdt.llm_call_card 宏渲染 LLM 调用:
- LLM 调用卡片: .sd-llm-card
- 工具批次: .sd-tool-group
- Payload 按钮: data-action="open-payload" 带 data-payload-id
"""

import pytest

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"
TIMELINE_FILE = COMPONENTS / "session_detail_timeline.html"
TIMELINE_DIR = COMPONENTS / "session_detail_timeline"


def _read_template_with_splits(main_file, split_dir):
    """Read main template file and all split subdirectory files (if they exist)."""
    parts = []
    if main_file.exists():
        parts.append(main_file.read_text(encoding="utf-8"))
    if split_dir.is_dir():
        for f in sorted(split_dir.glob("*.html")):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _timeline_component():
    return _read_template_with_splits(TIMELINE_FILE, TIMELINE_DIR)


def _primitives_component():
    return (COMPONENTS / "session_detail_primitives.html").read_text(encoding="utf-8")


# ── LLM 调用卡片结构 ──────────────────────────


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_has_llm_call_card():
    """时间线组件必须定义 llm_call_card 宏。"""
    source = _timeline_component()
    assert "macro llm_call_card" in source, (
        "Timeline must define llm_call_card macro"
    )


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_llm_call_card_has_header():
    """LLM call card must have header with title, model, status."""
    source = _timeline_component()
    assert "sd-card-head" in source, "Card must have header"
    assert "sd-card-title" in source, "Card must have title"
    assert "sd-llm-card" in source, "Must have llm card class"


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_llm_call_card_has_metrics():
    """LLM call card must have a metrics section."""
    source = _timeline_component()
    assert "sd-metrics" in source, "Card must have metrics section"


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_llm_call_card_has_payload_buttons():
    """LLM call card must have payload buttons."""
    source = _timeline_component()
    assert "open-payload" in source, "Card must have open-payload buttons"
    # data-payload-id 由 primitives 中的 sdp.button() 宏生成
    prim = _primitives_component()
    assert "data-payload-id" in prim, "Primitives must define data-payload-id"


# ── LLM 调用上下文中的工具调用 ──────────────────────────────────


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_tool_batch_macro_exists():
    """Timeline must have tool_batch macro."""
    source = _timeline_component()
    assert "macro tool_batch" in source, "Timeline must define tool_batch macro"


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_tool_batch_has_data_attrs():
    """Tool batch must have data attributes for identification."""
    source = _timeline_component()
    assert "data-tool-batch-id" in source, "Tool batch must have data-tool-batch-id"
    assert "data-tool-call-id" in source, "Tool rows must have data-tool-call-id"


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_tool_batch_has_result_buttons():
    """Tool rows must have payload result buttons."""
    source = _timeline_component()
    assert "open-payload" in source, "Tool rows must have open-payload buttons"


# ── Session uses component macros ───────────────────────────────────


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_session_uses_trace_round_macro():
    """session.html must use sdt.trace_round for rendering rounds."""
    source = _session_source()
    assert "sdt.trace_round" in source, "Session must use sdt.trace_round macro"


# ── Payload keys in view model ──────────────────────────────────────


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_payload_keys_in_routes():
    """View model must generate payload IDs for LLM calls."""
    base = Path(__file__).parents[2] / "src" / "session_browser" / "web"
    routes = (base / "routes.py").read_text(encoding="utf-8")
    view_model = (base / "session_detail" / "view_model.py").read_text(encoding="utf-8")
    source = routes + "\n" + view_model
    assert "context_payload_id" in source, "View model must generate context_payload_id"
    assert "response_payload_id" in source, "View model must generate response_payload_id"


# ── CSS classes ─────────────────────────────────────────────────────

_TIMELINE_CSS = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "static" / "css" / "session-detail.css"
_TIMELINE_CSS_DIR = _TIMELINE_CSS.parent / "session-detail"


def _read_css_with_splits(main_file, split_dir):
    """Read main CSS file and all split subdirectory files (if they exist)."""
    parts = []
    if main_file.exists():
        parts.append(main_file.read_text(encoding="utf-8"))
    if split_dir.is_dir():
        for f in sorted(split_dir.glob("*.css")):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _read_timeline_css():
    return _read_css_with_splits(_TIMELINE_CSS, _TIMELINE_CSS_DIR)


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_css_has_sd_llm_card_styles():
    """session-detail.css must contain card styles for LLM calls."""
    css = _read_timeline_css()
    # LLM card uses base .sd-card class + .sd-llm-body
    assert ".sd-card" in css, "CSS must define .sd-card styles"
    assert ".sd-card-head" in css, "CSS must define .sd-card-head styles"
    assert ".sd-card-title" in css, "CSS must define .sd-card-title styles"
    assert ".sd-llm-body" in css, "CSS must define .sd-llm-body styles"
    assert ".sd-metrics" in css, "CSS must define .sd-metrics styles"


@pytest.mark.contract_case("DATA-PRESENTER-009")
def test_css_has_tool_group_styles():
    """session-detail.css must contain .sd-tool-group styles."""
    css = _read_timeline_css()
    assert ".sd-tool-group" in css, "CSS must define .sd-tool-group styles"
    assert ".sd-tool-row" in css, "CSS must define .sd-tool-row styles"
