"""负责导出 Gate Presentation 阶段公开入口；不负责修改计划或执行状态。

由 CLI 的各个子命令调用。"""

from scripts.gates.presentation.terminal_ui import (
    render_explanation,
    render_gate_catalog,
    render_gate_plan,
    render_health_audit,
    render_run_receipt,
    render_terminal_event,
)

__all__ = (
    'render_explanation',
    'render_gate_catalog',
    'render_gate_plan',
    'render_health_audit',
    'render_run_receipt',
    'render_terminal_event',
)
