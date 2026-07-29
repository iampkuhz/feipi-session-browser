"""定义 Gate catalog 与 planner 使用的不可变 typed model。

不负责产品业务处理；由 Gate CLI 或 Stop pipeline 调用。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutorType(StrEnum):
    """标识 Gate 命令应交给哪类 executor adapter。"""

    COMMAND = 'command'
    GRADLE = 'gradle'


class IncrementalMode(StrEnum):
    """标识 Gate 在 changed-files 模式下的适用性策略。"""

    PATTERNS = 'patterns'
    ALWAYS = 'always'


class ChangedFilesInput(StrEnum):
    """声明 executor 是否可把 changed-files 传入 Gate 进程。"""

    NONE = 'none'
    ENVIRONMENT = 'environment'


@dataclass(frozen=True, slots=True)
class TargetCommand:
    """保存同一能力在某个 target 下的 argv。"""

    target: str
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OptionalCommandArgs:
    """保存仅在仓库路径存在时追加的 argv。"""

    path: str
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """保存 catalog 声明的命令模板与少量能力型动态参数。"""

    capability: str
    argv: tuple[str, ...]
    target_argv: tuple[TargetCommand, ...] = ()
    required_paths: tuple[str, ...] = ()
    existing_args: tuple[str, ...] = ()
    glob_args: tuple[str, ...] = ()
    optional_args: tuple[OptionalCommandArgs, ...] = ()
    prerequisite_tasks: tuple[str, ...] = ()
    existing_only: bool = False


@dataclass(frozen=True, slots=True)
class GateTargetRule:
    """保存一个 Gate 在某个 target 内的稳定顺序与增量 pattern。"""

    target: str
    order: int
    patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GateSpec:
    """保存逻辑 Gate 的唯一注册记录及全部执行/适用性元数据。"""

    name: str
    target_rules: tuple[GateTargetRule, ...]
    executor_type: ExecutorType
    command: CommandSpec | None
    gradle_tasks: tuple[str, ...]
    gradle_args: tuple[str, ...]
    java_rules: tuple[str, ...]
    timeout_seconds: int
    parallel_safe: bool
    exclusive_resources: tuple[str, ...]
    incremental_mode: IncrementalMode
    changed_files_input: ChangedFilesInput
    included_by: tuple[str, ...]
    tiers: tuple[str, ...]
    description: str
    network_failure: str = 'fail'

    # 返回 Gate 所属 target，顺序与 catalog 注册顺序一致。
    @property
    def targets(self) -> tuple[str, ...]:
        """返回：
        当前函数的稳定结果。
        """
        return tuple(rule.target for rule in self.target_rules)

    # 返回跨 target 去重后的增量 pattern。
    @property
    def patterns(self) -> tuple[str, ...]:
        """返回：
        当前函数的稳定结果。
        """
        return tuple(
            dict.fromkeys(pattern for rule in self.target_rules for pattern in rule.patterns)
        )


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """保存 target 的 dominance 与并发执行元数据。"""

    name: str
    includes: tuple[str, ...]
    parallel_safe: bool
    exclusive_resources: tuple[str, ...]
    timeout_seconds: int
    description: str


@dataclass(frozen=True, slots=True)
class PathRule:
    """保存 changed path 到分类与 quality target 的有序规则。"""

    category: str
    patterns: tuple[str, ...]
    requires_quality_gate: bool
    quality_target: str | None
    risk_level: str
    allowed_by_default: bool


@dataclass(frozen=True, slots=True)
class TierSpec:
    """保存 Gate tier 的稳定语义及成员选择方式。"""

    name: str
    description: str
    failure_policy: str
    gate_names: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class GateCatalog:
    """聚合 Gate、target、路径规则和 tier 的单一 typed catalog。"""

    version: str
    gates: tuple[GateSpec, ...]
    targets: tuple[TargetSpec, ...]
    path_rules: tuple[PathRule, ...]
    scan_script_smoke_patterns: tuple[str, ...]
    tiers: tuple[TierSpec, ...]


@dataclass(frozen=True, slots=True)
class FileClassification:
    """表示单个 repository path 的确定性分类结果。"""

    file: str
    category: str
    requires_quality_gate: bool
    quality_target: str | None
    risk_level: str
    allowed_by_default: bool


@dataclass(frozen=True, slots=True)
class TargetGatePlan:
    """保存一个 effective target 按 catalog 顺序选择的 Gate。"""

    target: str
    gates: tuple[GateSpec, ...]


@dataclass(frozen=True, slots=True)
class GatePlan:
    """冻结 changed-files 到 target 与 applicable Gate 的完整规划结果。"""

    changed_files: tuple[str, ...]
    classifications: tuple[FileClassification, ...]
    raw_targets: tuple[str, ...]
    effective_targets: tuple[str, ...]
    targets: tuple[TargetGatePlan, ...]

    # 按 target/注册顺序返回去重后的逻辑 Gate。
    @property
    def logical_gates(self) -> tuple[GateSpec, ...]:
        """返回：
        当前函数的稳定结果。
        """
        seen: set[str] = set()
        result: list[GateSpec] = []
        for target_plan in self.targets:
            for gate in target_plan.gates:
                if gate.name not in seen:
                    seen.add(gate.name)
                    result.append(gate)
        return tuple(result)


@dataclass(frozen=True, slots=True)
class PlannedGate:
    """冻结一个逻辑 Gate 的执行归属与状态来源。"""

    name: str
    target: str
    group_id: str
    status_source: str
    resources: tuple[str, ...]
    parallel_safe: bool
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class CommandGroup:
    """冻结一次顶层进程调用及其逻辑 Gate、资源和依赖。"""

    group_id: str
    kind: str
    command: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    gate_names: tuple[str, ...]
    resources: tuple[str, ...]
    parallel_safe: bool
    timeout_seconds: int
    depends_on: tuple[str, ...] = ()
    aggregation_reason: str = ''


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """保存 executor 唯一消费的确定性、不可变、可哈希执行计划。"""

    plan_id: str
    fingerprint: str
    gate_plan: GatePlan
    gates: tuple[PlannedGate, ...]
    groups: tuple[CommandGroup, ...]

    @property
    def logical_gates(self) -> tuple[GateSpec, ...]:
        """返回原始 Gate plan 的去重逻辑 Gate。"""
        return self.gate_plan.logical_gates
