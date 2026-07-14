"""负责旧 pipeline import 的薄兼容入口；不得新增状态、Gate 或恢复业务。"""

from scripts.agent_runtime.change.entry import run_stop_payload


def run_stop(agent, raw_context, **_kwargs):
    """转发旧 pipeline 调用并返回统一退出码；不执行任何收口步骤。"""
    return run_stop_payload(agent, raw_context)[0]


__all__ = ['run_stop']
