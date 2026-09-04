"""负责纯展示 Gate catalog、计划、事件与 receipt；不负责修改执行状态。

由 CLI 的 list、explain、plan、run 和 health 子命令调用。"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from scripts.gates.catalog.gate_contracts import Gate, GateCatalog, TargetPreset

if TYPE_CHECKING:
    from scripts.gates.planning import GatePlan

_EVENT_KINDS = frozenset({'PLAN', 'START', 'HEARTBEAT', 'STALL', 'RESULT', 'DONE'})
_FORMATS = frozenset({'human', 'json'})
_EVENT_FIELD_ORDER = (
    'run',
    'gate',
    'recipe_step',
    'invocation',
    'elapsed_seconds',
    'status',
    'reason',
    'log',
    'process_count',
)


class ReceiptView(Protocol):
    """Presentation 读取的最小 receipt 视图，避免阶段间实现依赖。"""

    schema_version: int
    run_id: str
    status: str
    reason: str
    duration_ms: int
    plan_fingerprint: str
    summary_path: Path
    canonical_rerun: str


class HealthAuditView(Protocol):
    """Presentation 读取的最小 health 视图。"""

    status: object
    reason: str
    doctor_result: object
    gate_results: tuple[object, ...]
    over_target_gates: tuple[str, ...]
    receipt: ReceiptView


def _public_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _public_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_public_value(item) for item in value]
    return value


def _render_json(payload: object) -> str:
    return json.dumps(_public_value(payload), ensure_ascii=False, indent=2, sort_keys=True)


def _require_format(output_format: str) -> None:
    if output_format not in _FORMATS:
        raise ValueError(f'unsupported format: {output_format}')


def _gate_payload(gate: Gate) -> dict[str, Any]:
    """把单个 Gate 契约转成稳定的公开展示结构。"""
    return {
        'id': gate.name,
        'description': gate.description,
        'targetPresets': list(gate.target_presets),
        'trigger': {'mode': gate.trigger.mode.value, 'patterns': list(gate.trigger.paths)},
        'durationTargetsSeconds': {
            'incremental': gate.recipe.duration_expectations.incremental,
            'full': gate.recipe.duration_expectations.full,
        },
        'recipeSteps': [
            {
                'name': step.name,
                'kind': step.kind.value,
                'checkId': step.check_id,
            }
            for step in gate.recipe.steps
        ],
    }


def _target_payload(target: TargetPreset, catalog: GateCatalog) -> dict[str, Any]:
    return {
        'id': target.name,
        'description': target.description,
        'gates': [gate.name for gate in catalog.gates if target.name in gate.target_presets],
    }


def render_gate_catalog(catalog: GateCatalog, *, output_format: str = 'human') -> str:
    """展示唯一 Gate 与 TargetPreset 清单。"""

    _require_format(output_format)
    payload = {
        'gates': [_gate_payload(gate) for gate in catalog.gates],
        'targetPresets': [_target_payload(target, catalog) for target in catalog.target_presets],
    }
    if output_format == 'json':
        return _render_json(payload)
    lines = [f'GATES count={len(catalog.gates)}']
    for gate in catalog.gates:
        targets = ','.join(gate.target_presets) or '-'
        lines.append(
            f'- {gate.name}: {gate.description} '
            f'[trigger={gate.trigger.mode.value}; targets={targets}]'
        )
    lines.append(f'TARGET_PRESETS count={len(catalog.target_presets)}')
    for target in catalog.target_presets:
        gates = ','.join(gate.name for gate in catalog.gates if target.name in gate.target_presets)
        lines.append(f'- {target.name}: {target.description} [gates={gates or "-"}]')
    return '\n'.join(lines)


def render_explanation(
    subject: Gate | TargetPreset,
    catalog: GateCatalog,
    *,
    output_format: str = 'human',
) -> str:
    """解释一个 Gate 或 TargetPreset 的声明，不执行或重新规划。"""

    _require_format(output_format)
    if isinstance(subject, Gate):
        payload = {'kind': 'gate', **_gate_payload(subject)}
        if output_format == 'json':
            return _render_json(payload)
        lines = [
            f'GATE id={subject.name}',
            f'description={subject.description}',
            f'trigger={subject.trigger.mode.value}',
        ]
        lines.extend(f'pattern={pattern}' for pattern in subject.trigger.paths)
        lines.append(f'targetPresets={",".join(subject.target_presets) or "-"}')
        lines.append(
            'durationTargetsSeconds='
            f'incremental:{subject.recipe.duration_expectations.incremental},'
            f'full:{subject.recipe.duration_expectations.full}'
        )
        lines.extend(
            f'recipeStep={step.name} kind={step.kind.value}'
            + (f' check={step.check_id}' if step.check_id else '')
            for step in subject.recipe.steps
        )
        return '\n'.join(lines)

    payload = {'kind': 'targetPreset', **_target_payload(subject, catalog)}
    if output_format == 'json':
        return _render_json(payload)
    gates = payload['gates']
    return '\n'.join(
        (
            f'TARGET_PRESET id={subject.name}',
            f'description={subject.description}',
            f'gates={",".join(gates) or "-"}',
        )
    )


def _plan_payload(plan: GatePlan) -> dict[str, Any]:
    return {
        'mode': plan.mode.value,
        'snapshot': {
            'source': plan.snapshot.source,
            'head': plan.snapshot.head,
            'base': plan.snapshot.base,
            'files': list(plan.snapshot.files),
            'contentFingerprint': plan.snapshot.content_fingerprint,
        },
        'selector': (
            {'kind': plan.selector_kind, 'value': plan.selector_value}
            if plan.selector_kind and plan.selector_value
            else None
        ),
        'matches': [
            {'file': item.file, 'pattern': item.pattern, 'gate': item.gate_name}
            for item in plan.matches
        ],
        'notTriggered': [
            {'gate': item.gate_name, 'reason': item.reason} for item in plan.not_triggered
        ],
        'gates': [
            {
                'id': gate.name,
                'durationTargetSeconds': gate.recipe.duration_for(plan.mode),
                'recipeSteps': [
                    {'name': step.name, 'kind': step.kind.value} for step in gate.recipe.steps
                ],
            }
            for gate in plan.gates
        ],
        'commandInvocations': [
            {
                'invocationId': item.invocation_id,
                'gate': item.gate_name,
                'recipeStep': item.recipe_step_name,
                'kind': item.kind,
                'argv': list(item.argv),
            }
            for item in plan.command_invocations
        ],
        'processCount': plan.process_count,
    }


def render_gate_plan(plan: GatePlan, *, output_format: str = 'human') -> str:
    """展示冻结计划的输入、选择因果、步骤、进程数与时效目标。"""

    _require_format(output_format)
    payload = _plan_payload(plan)
    if output_format == 'json':
        return _render_json(payload)
    snapshot = plan.snapshot
    lines = [
        f'PLAN mode={plan.mode.value} source={snapshot.source} '
        f'head={snapshot.head or "-"} base={snapshot.base or "-"} '
        f'files={len(snapshot.files)} gates={len(plan.gates)} processes={plan.process_count}',
        f'CONTENT_FINGERPRINT {snapshot.content_fingerprint}',
    ]
    lines.extend(f'INPUT file={path}' for path in snapshot.files)
    lines.extend(
        f'MATCH file={item.file} pattern={item.pattern} gate={item.gate_name}'
        for item in plan.matches
    )
    lines.extend(
        f'NOT_TRIGGERED gate={item.gate_name} reason={item.reason}' for item in plan.not_triggered
    )
    for gate in plan.gates:
        lines.append(
            f'GATE id={gate.name} target_seconds={gate.recipe.duration_for(plan.mode)} '
            f'recipe_steps={len(gate.recipe.steps)}'
        )
    for gate in plan.gates:
        for step in gate.recipe.steps:
            owned = tuple(
                item
                for item in plan.command_invocations
                if item.gate_name == gate.name and item.recipe_step_name == step.name
            )
            lines.append(
                f'RECIPE_STEP gate={gate.name} step={step.name} kind={step.kind.value} '
                f'processes={len(owned)}'
            )
            lines.extend(
                f'COMMAND invocation={item.invocation_id} command={shlex.join(item.argv)}'
                for item in owned
            )
    return '\n'.join(lines)


def render_terminal_event(
    event: str, fields_map: Mapping[str, object] | None = None, **fields_values: object
) -> str:
    """把稳定事件渲染为一行 stderr 文本；不解释或改写状态。"""

    kind = str(event).upper()
    if kind not in _EVENT_KINDS:
        raise ValueError(f'unsupported terminal event: {event}')
    values = dict(fields_map or {})
    values.update(fields_values)
    rendered = [kind]
    ordered_keys = [key for key in _EVENT_FIELD_ORDER if key in values]
    ordered_keys.extend(sorted(set(values) - set(ordered_keys)))
    for key in ordered_keys:
        value = values[key]
        if value is None or value == '':
            continue
        normalized = str(value.value if isinstance(value, Enum) else value)
        rendered.append(f'{key}={shlex.quote(normalized)}')
    return ' '.join(rendered)


def render_run_receipt(receipt: ReceiptView, *, output_format: str = 'human') -> str:
    """展示一次已持久化运行的最终状态和可复现入口。"""

    _require_format(output_format)
    payload = {
        'schemaVersion': receipt.schema_version,
        'runId': receipt.run_id,
        'status': receipt.status,
        'reason': receipt.reason,
        'durationMs': receipt.duration_ms,
        'planFingerprint': receipt.plan_fingerprint,
        'summaryPath': str(receipt.summary_path),
        'canonicalRerun': receipt.canonical_rerun,
    }
    if output_format == 'json':
        return _render_json(payload)
    reason = f' reason={receipt.reason}' if receipt.reason else ''
    return (
        f'DONE run={receipt.run_id} status={receipt.status}{reason} '
        f'duration_ms={receipt.duration_ms} receipt={receipt.summary_path} '
        f'rerun={shlex.quote(receipt.canonical_rerun)}'
    )


def render_health_audit(audit: HealthAuditView, *, output_format: str = 'human') -> str:
    """展示 health 审计，不把超时效或 doctor 问题改写成 Gate PASS。"""

    _require_format(output_format)
    status = str(audit.status)
    doctor_status = str(getattr(audit.doctor_result, 'status', 'FAIL'))
    passed = sum(str(getattr(item, 'status', '')) == 'PASS' for item in audit.gate_results)
    payload = {
        'status': status,
        'reason': audit.reason,
        'doctorStatus': doctor_status,
        'gateCount': len(audit.gate_results),
        'passedGateCount': passed,
        'overTargetGates': list(audit.over_target_gates),
        'receipt': str(audit.receipt.summary_path),
    }
    if output_format == 'json':
        return _render_json(payload)
    reason = f' reason={audit.reason}' if audit.reason else ''
    return (
        f'GATE_HEALTH status={status}{reason} doctor={doctor_status} '
        f'gates={passed}/{len(audit.gate_results)} '
        f'over_target={len(audit.over_target_gates)} receipt={audit.receipt.summary_path}'
    )
