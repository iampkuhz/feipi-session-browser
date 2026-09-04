"""负责定义 Catalog 阶段公开的不可变 Gate 契约；不负责创建领域声明。

由 Catalog、Planning、Execution 和 Presentation 阶段调用。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionMode(StrEnum):
    """Gate 唯一允许的两种执行范围。"""

    INCREMENTAL = 'incremental'
    FULL = 'full'


class TriggerMode(StrEnum):
    """自动增量规划时 Gate 的触发方式。"""

    ALWAYS = 'always'
    CHANGED = 'changed'


class RecipeStepKind(StrEnum):
    """RecipeStep 可交给执行阶段的六种 owner adapter。"""

    COMMAND = 'command'
    PYTHON_CHECK = 'python-check'
    GRADLE_TASK = 'gradle-task'
    JAVA_RULE = 'java-rule'
    PLAYWRIGHT = 'playwright'
    SCAN_SMOKE = 'scan-smoke'


@dataclass(frozen=True, slots=True)
class GateTrigger:
    """声明 Gate 在无 selector 的 incremental 计划中何时被选中。"""

    mode: TriggerMode
    paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DurationExpectations:
    """保存 incremental/full 两个非阻断时效目标。"""

    incremental: int
    full: int

    def for_mode(self, mode: ExecutionMode | str) -> int:
        """返回指定执行范围的维护目标；该值不是 timeout。"""

        selected = ExecutionMode(mode)
        return self.incremental if selected is ExecutionMode.INCREMENTAL else self.full


@dataclass(frozen=True, slots=True)
class RecipeStep:
    """保存一个具有唯一 owner 的 Gate recipe 步骤。"""

    name: str
    kind: RecipeStepKind
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
class GateRecipe:
    """绑定唯一 recipe 与不影响选步的时效目标。"""

    duration_expectations: DurationExpectations
    steps: tuple[RecipeStep, ...]

    def duration_for(self, mode: ExecutionMode | str) -> int:
        """返回指定执行范围的非阻断时效目标。"""

        return self.duration_expectations.for_mode(mode)


@dataclass(frozen=True, slots=True)
class Gate:
    """用户可见逻辑门的唯一声明。"""

    name: str
    description: str
    trigger: GateTrigger
    target_presets: tuple[str, ...]
    recipe: GateRecipe


@dataclass(frozen=True, slots=True)
class TargetPreset:
    """描述人工选择的一组 Gate，不表示耗时或执行强度。"""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class GateCatalog:
    """按声明顺序保存唯一 TargetPreset 与 Gate 清单。"""

    target_presets: tuple[TargetPreset, ...]
    gates: tuple[Gate, ...]
