"""负责旧 Stop import 的薄兼容入口；不负责业务，统一委托 change.entry。"""

from scripts.agent_runtime.change.entry import main, read_stdin_once, run_stop_payload


def run_stop(agent, raw_context, **_kwargs):
    """转发旧 Stop 调用并返回统一退出码；不处理 Git 或 Gate。"""
    return run_stop_payload(agent, raw_context)[0]


__all__ = ['main', 'read_stdin_once', 'run_stop']
