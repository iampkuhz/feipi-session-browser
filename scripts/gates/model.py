"""定义 Gate Catalog、Planner 与 Executor 共用的不可变领域模型。

这里仅描述“配置是什么”和“计划选中了什么”。配置解析、Gate 选择和进程执行分别由
``catalog``、``planner`` 和 ``executor`` 调用这些类型完成协作。本模块不负责配置解析、
选择或执行，避免领域模型夹带隐式决策。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionMode(StrEnum):
    """Gate 唯一允许的两种执行模式。"""

    INCREMENTAL = 'incremental'
    FULL = 'full'


class TriggerMode(StrEnum):
    """自动增量规划时，Gate 的触发方式。"""

    ALWAYS = 'always'
    CHANGED = 'changed'


class RunKind(StrEnum):
    """区分 Executor 支持的六种 typed adapter。"""

    COMMAND = 'command'
    PYTHON_CHECK = 'python-check'
    GRADLE_TASK = 'gradle-task'
    JAVA_RULE = 'java-rule'
    PLAYWRIGHT = 'playwright'
    SCAN_SMOKE = 'scan-smoke'


@dataclass(frozen=True, slots=True)
class GateTrigger:
    """声明 Gate 在无 selector 的 incremental 模式下何时被选中。"""

    mode: TriggerMode
    paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunProfile:
    """保存一种 mode 的完整执行参数与 Gate 自己维护的时效目标。"""

    target_seconds: int
    timeout_seconds: int
    argv: tuple[str, ...] = ()
    required_paths: tuple[str, ...] = ()
    append_globs: tuple[str, ...] = ()
    check_id: str | None = None
    runtime: str = 'system'
    args: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    prerequisite_tasks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RunSpec:
    """保存一种 adapter 及其互不推断的 incremental/full profile。"""

    kind: RunKind
    incremental: RunProfile
    full: RunProfile

    def profile_for(self, mode: ExecutionMode | str) -> RunProfile:
        """返回明确 mode 对应的 profile，不做 fallback 或自动升级。"""

        selected = ExecutionMode(mode)
        return self.incremental if selected is ExecutionMode.INCREMENTAL else self.full


@dataclass(frozen=True, slots=True)
class GateSpec:
    """保存一个 Gate 的最小五字段协议。"""

    name: str
    description: str
    trigger: GateTrigger
    targets: tuple[str, ...]
    run: RunSpec


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """描述一个只供人工选择的 Gate preset。"""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class PathRule:
    """描述路径的风险分类；它不再决定 Target 或 Gate。"""

    category: str
    patterns: tuple[str, ...]
    risk_level: str
    allowed: bool


@dataclass(frozen=True, slots=True)
class FileClassification:
    """保存路径经过首个命中规则后的治理分类。"""

    file: str
    category: str
    risk_level: str
    allowed: bool


@dataclass(frozen=True, slots=True)
class GateCatalog:
    """按声明顺序保存当前唯一的 Target 与 Gate 清单。"""

    targets: tuple[TargetSpec, ...]
    gates: tuple[GateSpec, ...]
    path_rules: tuple[PathRule, ...]


@dataclass(frozen=True, slots=True)
class GatePlan:
    """保存 Planner 已冻结的 mode、输入和有序 Gate 列表。"""

    mode: ExecutionMode
    changed_files: tuple[str, ...]
    gates: tuple[GateSpec, ...]
    selector: str | None = None
    selector_value: str | None = None

    @property
    def logical_gates(self) -> tuple[GateSpec, ...]:
        """为执行与报告层提供语义明确的只读 Gate 列表。"""

        return self.gates


@dataclass(frozen=True, slots=True)
class PlannedGate:
    """描述逻辑 Gate 与实际命令组之间的执行归属。"""

    name: str
    target: str
    group_id: str
    status_source: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class CommandGroup:
    """保存执行器可直接运行的一条有界命令。"""

    group_id: str
    kind: str
    command: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    gate_names: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """封装可复现的 Gate 逻辑计划和实际命令执行计划。"""

    plan_id: str
    fingerprint: str
    gate_plan: GatePlan
    gates: tuple[PlannedGate, ...]
    groups: tuple[CommandGroup, ...]

    @property
    def logical_gates(self) -> tuple[GateSpec, ...]:
        """透传底层逻辑计划中的 Gate 列表。"""

        return self.gate_plan.logical_gates
