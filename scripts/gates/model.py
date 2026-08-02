"""负责定义 Gate catalog、planner 与 executor 共用的不可变数据模型。

本模块不负责解析配置或执行命令，只为 Gate 规划与执行阶段提供稳定的数据边界。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChangedFilesInput(StrEnum):
    """声明执行命令是否需要通过环境变量接收变更文件列表。"""

    NONE = 'none'
    ENVIRONMENT = 'environment'


class MinimumTier(StrEnum):
    """定义 Gate 可被纳入执行计划的最低检查层级。"""

    QUICK = 'quick'
    REQUIRED = 'required'
    FULL = 'full'


class RunKind(StrEnum):
    """区分执行器支持的命令构造方式，避免依赖名称推断行为。"""

    COMMAND = 'command'
    PYTHON_CHECK = 'python-check'
    PLAYWRIGHT = 'playwright'
    SCAN_SMOKE = 'scan-smoke'
    GRADLE_TASK = 'gradle-task'
    JAVA_RULE = 'java-rule'


@dataclass(frozen=True, slots=True)
class OptionalCommandArgs:
    """保存仅在指定路径存在时追加的一组命令参数。"""

    path: str
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunSpec:
    """一种稳定且与 target 无关的执行声明。"""

    kind: RunKind
    argv: tuple[str, ...] = ()
    check: str | None = None
    python: str = 'system'
    args: tuple[str, ...] = ()
    required_paths: tuple[str, ...] = ()
    glob_args: tuple[str, ...] = ()
    optional_args: tuple[OptionalCommandArgs, ...] = ()
    prerequisite_tasks: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    java_rules: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GateTargetRule:
    """描述一个 Gate 在指定 target 中的顺序和增量匹配范围。"""

    target: str
    order: int
    patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GateSpec:
    """保存单个逻辑 Gate 的执行声明、触发规则与失败策略。"""

    name: str
    target_rules: tuple[GateTargetRule, ...]
    run: RunSpec
    timeout_seconds: int
    changed_files_input: ChangedFilesInput
    minimum_tier: MinimumTier
    description: str
    network_failure: str

    @property
    def targets(self) -> tuple[str, ...]:
        """按声明顺序返回该 Gate 参与的全部 target，不负责去重。"""

        return tuple(rule.target for rule in self.target_rules)

    @property
    def patterns(self) -> tuple[str, ...]:
        """合并各 target 的文件模式，并保留首次出现的顺序。"""

        return tuple(dict.fromkeys(p for rule in self.target_rules for p in rule.patterns))


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """描述一个验证场景及其显式包含的其他 target。"""

    name: str
    includes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PathRule:
    """把一组文件模式映射到风险分类和有序验证场景。"""

    category: str
    patterns: tuple[str, ...]
    targets: tuple[str, ...]
    risk_level: str
    allowed: bool

    @property
    def requires_quality_gate(self) -> bool:
        """判断该路径规则是否要求进入至少一个质量验证场景。"""

        return bool(self.targets)


@dataclass(frozen=True, slots=True)
class GateDefaults:
    """保存 Gate 未显式声明时采用的集中默认值。"""

    minimum_tier: MinimumTier
    timeout_seconds: int
    changed_files_input: ChangedFilesInput
    network_failure: str


@dataclass(frozen=True, slots=True)
class GateCatalog:
    """汇总已校验的 Gate、target、路径规则和场景触发规则。"""

    version: str
    gate_defaults: GateDefaults
    gates: tuple[GateSpec, ...]
    targets: tuple[TargetSpec, ...]
    path_rules: tuple[PathRule, ...]
    target_triggers: tuple[TargetTrigger, ...]


@dataclass(frozen=True, slots=True)
class TargetTrigger:
    """声明命中文件模式时额外启用的验证场景。"""

    target: str
    patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileClassification:
    """保存单个变更文件经过路径规则判定后的分类结果。"""

    file: str
    category: str
    targets: tuple[str, ...]
    risk_level: str
    allowed: bool

    @property
    def requires_quality_gate(self) -> bool:
        """判断该文件是否被分配到至少一个质量验证场景。"""

        return bool(self.targets)


@dataclass(frozen=True, slots=True)
class TargetGatePlan:
    """保存一个验证场景最终选中的有序 Gate 列表。"""

    target: str
    gates: tuple[GateSpec, ...]


@dataclass(frozen=True, slots=True)
class GatePlan:
    """保存文件分类、有效 target 与各场景 Gate 的完整逻辑计划。"""

    changed_files: tuple[str, ...]
    classifications: tuple[FileClassification, ...]
    raw_targets: tuple[str, ...]
    effective_targets: tuple[str, ...]
    targets: tuple[TargetGatePlan, ...]

    @property
    def logical_gates(self) -> tuple[GateSpec, ...]:
        """按场景顺序汇总逻辑 Gate，并以 Gate 名称稳定去重。"""

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
    """描述逻辑 Gate 与实际命令组之间的执行归属。"""

    name: str
    target: str
    group_id: str
    status_source: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class CommandGroup:
    """保存执行器可直接运行的一组命令及其聚合信息。"""

    group_id: str
    kind: str
    command: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    gate_names: tuple[str, ...]
    timeout_seconds: int
    aggregation_reason: str = ''


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
        """透传底层逻辑计划中的稳定去重 Gate 列表。"""

        return self.gate_plan.logical_gates
