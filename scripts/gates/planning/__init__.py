"""Gate Planning 阶段的公开契约。

本模块只汇出输入快照、Trigger 匹配和计划编译入口；不负责声明 Gate 或执行进程。
由 CLI、Execution、Evidence 和 Presentation 通过这里的稳定类型进行阶段协作。
"""

from scripts.gates.planning.change_snapshot import ChangeSnapshot, capture_change_snapshot
from scripts.gates.planning.plan_compiler import (
    CommandInvocation,
    GatePlan,
    compile_gate_plan,
)
from scripts.gates.planning.trigger_matcher import (
    NotTriggeredGate,
    TriggerMatch,
    match_trigger,
)

__all__ = (
    'ChangeSnapshot',
    'CommandInvocation',
    'GatePlan',
    'NotTriggeredGate',
    'TriggerMatch',
    'capture_change_snapshot',
    'compile_gate_plan',
    'match_trigger',
)
