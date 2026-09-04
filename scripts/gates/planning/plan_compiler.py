"""从 Catalog 声明与 ChangeSnapshot 编译唯一不可变 GatePlan。

本模块只负责 mode×selector、Trigger 因果和进程声明的冻结；不采集输入，不启动
OS 进程或分类结果。由 CLI 调用，Execution adapter 可在编译时注入 CommandInvocation。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from scripts.gates.catalog.gate_contracts import ExecutionMode, Gate, RecipeStep, TriggerMode
from scripts.gates.catalog.registry import GATES, gate_by_name, target_preset_by_name
from scripts.gates.planning.trigger_matcher import NotTriggeredGate, TriggerMatch, match_trigger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scripts.gates.planning.change_snapshot import ChangeSnapshot


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """描述冻结到 GatePlan 的一个真实 OS 进程。"""

    invocation_id: str
    kind: str
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    gate_name: str
    recipe_step_name: str


class InvocationFactory(Protocol):
    """由 Execution 实现并在编译唯一计划时注入的 adapter。"""

    def __call__(self, gate: Gate, recipe_step: RecipeStep) -> Iterable[CommandInvocation]: ...


@dataclass(frozen=True, slots=True)
class GatePlan:
    """冻结输入、选择原因、recipe 和真实进程调用。"""

    mode: ExecutionMode
    snapshot: ChangeSnapshot
    gates: tuple[Gate, ...]
    matches: tuple[TriggerMatch, ...]
    not_triggered: tuple[NotTriggeredGate, ...]
    selector_kind: str | None = None
    selector_value: str | None = None
    command_invocations: tuple[CommandInvocation, ...] = ()

    @property
    def logical_gates(self) -> tuple[Gate, ...]:
        """返回有序的逻辑 Gate 选择。"""

        return self.gates

    @property
    def changed_files(self) -> tuple[str, ...]:
        """返回精确冻结的 changed files，不创建第二种输入模型。"""

        return self.snapshot.files

    @property
    def process_count(self) -> int:
        """返回这个冻结计划中的真实 OS 进程数。"""

        return len(self.command_invocations)

    def command_invocations_for(self, gate_name: str) -> tuple[CommandInvocation, ...]:
        """按 recipe 顺序返回一个 Gate 的进程调用。"""

        return tuple(
            invocation
            for invocation in self.command_invocations
            if invocation.gate_name == gate_name
        )


def _gates_for_target(target: str) -> tuple[Gate, ...]:
    """按 Catalog 顺序展开一个已校验的 TargetPreset。"""

    target_preset_by_name(target)
    selected = tuple(gate for gate in GATES if target in gate.target_presets)
    if not selected:
        raise ValueError(f'quality TargetPreset selects no Gate: {target}')
    return selected


def _compile_invocations(
    gates: tuple[Gate, ...], invocation_factory: InvocationFactory | None
) -> tuple[CommandInvocation, ...]:
    if invocation_factory is None:
        return ()
    invocations: list[CommandInvocation] = []
    identifiers: set[str] = set()
    for gate in gates:
        for recipe_step in gate.recipe.steps:
            for invocation in invocation_factory(gate, recipe_step):
                if invocation.gate_name != gate.name:
                    raise ValueError(
                        f'CommandInvocation {invocation.invocation_id} belongs to wrong Gate'
                    )
                if invocation.recipe_step_name != recipe_step.name:
                    raise ValueError(
                        f'CommandInvocation {invocation.invocation_id} belongs to wrong RecipeStep'
                    )
                if invocation.invocation_id in identifiers:
                    raise ValueError(f'duplicate CommandInvocation id: {invocation.invocation_id}')
                identifiers.add(invocation.invocation_id)
                invocations.append(invocation)
    return tuple(invocations)


def compile_gate_plan(
    snapshot: ChangeSnapshot,
    *,
    mode: ExecutionMode | str = ExecutionMode.INCREMENTAL,
    target: str | None = None,
    gate: str | None = None,
    invocation_factory: InvocationFactory | None = None,
) -> GatePlan:
    """编译 mode×selector 矩阵，并保留每个选择原因。"""

    if target is not None and gate is not None:
        raise ValueError('target and gate selectors are mutually exclusive')
    selected_mode = ExecutionMode(mode)
    if selected_mode is ExecutionMode.FULL:
        if snapshot.source != 'full' or snapshot.files:
            raise ValueError('full mode requires a full snapshot without changed files')
    elif snapshot.source == 'full':
        raise ValueError('incremental mode requires an incremental ChangeSnapshot')
    if selected_mode is ExecutionMode.INCREMENTAL and (target or gate) and not snapshot.files:
        raise ValueError('incremental selector has no input; use full mode')

    matches = (
        match_trigger(snapshot.files, GATES) if selected_mode is ExecutionMode.INCREMENTAL else ()
    )
    selector_kind: str | None = None
    selector_value: str | None = None
    if gate is not None:
        selected = (gate_by_name(gate),)
        selector_kind, selector_value = 'gate', gate
    elif target is not None:
        selected = _gates_for_target(target)
        selector_kind, selector_value = 'target', target
    elif selected_mode is ExecutionMode.FULL:
        selected = GATES
    else:
        matched_names = {match.gate_name for match in matches}
        selected = tuple(
            candidate
            for candidate in GATES
            if candidate.trigger.mode is TriggerMode.ALWAYS or candidate.name in matched_names
        )

    selected_names = {candidate.name for candidate in selected}
    reason = 'excluded-by-selector' if selector_kind else 'no-trigger-pattern-matched'
    not_triggered = tuple(
        NotTriggeredGate(candidate.name, reason)
        for candidate in GATES
        if candidate.name not in selected_names
    )
    invocations = _compile_invocations(selected, invocation_factory)
    return GatePlan(
        mode=selected_mode,
        snapshot=snapshot,
        gates=selected,
        matches=matches,
        not_triggered=not_triggered,
        selector_kind=selector_kind,
        selector_value=selector_value,
        command_invocations=invocations,
    )
