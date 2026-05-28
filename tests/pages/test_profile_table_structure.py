"""验证 Trace 面板 DOM 结构的测试（v9）。
v9 使用基于组件的 Jinja2 宏：
- Round 通过 sdt.trace_round 宏渲染
- 工具调用通过 sdt.tool_batch 宏渲染
- 无内联 llm-call-detail 展开
- 通过按钮上的 open-payload 操作进行工具检查
"""

import pytest

from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
COMPONENTS = TEMPLATE_DIR / "components"


def _session_source():
    return (TEMPLATE_DIR / "session.html").read_text(encoding="utf-8")


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


def _primitives_component():
    return (COMPONENTS / "session_detail_primitives.html").read_text(encoding="utf-8")


# ── 无旧的内联详情模式 ───────────────────────────────────
