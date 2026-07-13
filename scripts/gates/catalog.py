"""负责从唯一声明式文件加载并校验 typed Gate catalog；不负责规划或执行 Gate；由 planner 调用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from scripts.gates.model import (
    ChangedFilesInput,
    CommandSpec,
    ExecutorType,
    GateCatalog,
    GateSpec,
    GateTargetRule,
    IncrementalMode,
    OptionalCommandArgs,
    PathRule,
    ReceiptPolicy,
    TargetCommand,
    TargetSpec,
    TierSpec,
)

_CATALOG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'gates.yaml'


def _mapping(value: Any, label: str) -> dict[str, Any]:
    """校验并返回 YAML mapping。"""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f'{label} must be a mapping')
    return value


def _items(value: Any, label: str) -> list[Any]:
    """校验并返回 YAML sequence。"""
    if not isinstance(value, list):
        raise ValueError(f'{label} must be a sequence')
    return value


def _strings(value: Any, label: str) -> tuple[str, ...]:
    """校验并冻结字符串 sequence。"""
    items = _items(value, label)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f'{label} must contain strings')
    return tuple(items)


def _command(raw: Any, label: str) -> CommandSpec:
    """把命令声明冻结为 typed model。"""
    row = _mapping(raw, label)
    targets = _mapping(row.get('target_argv', {}), f'{label}.target_argv')
    optional = tuple(
        OptionalCommandArgs(
            path=str(item['path']),
            argv=_strings(item.get('argv', []), f'{label}.optional_args.argv'),
        )
        for value in _items(row.get('optional_args', []), f'{label}.optional_args')
        for item in (_mapping(value, f'{label}.optional_args[]'),)
    )
    return CommandSpec(
        capability=str(row.get('capability', 'command')),
        argv=_strings(row.get('argv', []), f'{label}.argv'),
        target_argv=tuple(
            TargetCommand(str(target), _strings(argv, f'{label}.target_argv.{target}'))
            for target, argv in targets.items()
        ),
        required_paths=_strings(row.get('required_paths', []), f'{label}.required_paths'),
        existing_args=_strings(row.get('existing_args', []), f'{label}.existing_args'),
        glob_args=_strings(row.get('glob_args', []), f'{label}.glob_args'),
        optional_args=optional,
        full_args=_strings(row.get('full_args', []), f'{label}.full_args'),
        prerequisite_tasks=_strings(
            row.get('prerequisite_tasks', []), f'{label}.prerequisite_tasks'
        ),
        gradle_outcome_tasks=_strings(
            row.get('gradle_outcome_tasks', []), f'{label}.gradle_outcome_tasks'
        ),
        existing_only=bool(row.get('existing_only', False)),
    )


def _target(raw: Any) -> TargetSpec:
    """加载单条 target 声明。"""
    row = _mapping(raw, 'targets[]')
    return TargetSpec(
        name=str(row['name']),
        includes=_strings(row.get('includes', []), 'target.includes'),
        parallel_safe=bool(row['parallel']),
        exclusive_resources=_strings(row.get('resources', []), 'target.resources'),
        timeout_seconds=int(row['timeout']),
        description=str(row['description']),
    )


def _gate(raw: Any) -> GateSpec:
    """加载单条完整 Gate 声明。"""
    row = _mapping(raw, 'gates[]')
    rules = tuple(
        GateTargetRule(
            target=str(rule['name']),
            order=int(rule['order']),
            patterns=_strings(rule.get('patterns', []), 'gate.targets.patterns'),
        )
        for value in _items(row['targets'], 'gate.targets')
        for rule in (_mapping(value, 'gate.targets[]'),)
    )
    command = _command(row['command'], f"gate.{row['name']}.command") if 'command' in row else None
    gradle = _mapping(row.get('gradle', {}), f"gate.{row['name']}.gradle")
    tasks = _strings(gradle.get('tasks', []), 'gate.gradle.tasks')
    if bool(command) == bool(tasks):
        raise ValueError(f"Gate needs exactly one command source: {row['name']}")
    return GateSpec(
        name=str(row['name']),
        target_rules=rules,
        executor_type=ExecutorType.COMMAND if command else ExecutorType.GRADLE,
        command=command,
        gradle_tasks=tasks,
        gradle_args=_strings(gradle.get('args', []), 'gate.gradle.args'),
        timeout_seconds=int(row['timeout']),
        parallel_safe=bool(row['parallel']),
        exclusive_resources=_strings(row.get('resources', []), 'gate.resources'),
        incremental_mode=IncrementalMode(str(row['incremental'])),
        changed_files_input=ChangedFilesInput(str(row['changed_files'])),
        included_by=_strings(row.get('included_by', []), 'gate.included_by'),
        tiers=_strings(row['tiers'], 'gate.tiers'),
        receipt_policy=ReceiptPolicy(str(row['receipt'])),
        description=str(row['description']),
        network_failure=str(row.get('network_failure', 'fail')),
    )


def _load_catalog() -> GateCatalog:
    """读取 catalog YAML，校验顶层 schema 并构造不可变模型。"""
    try:
        raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding='utf-8'))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f'cannot load {_CATALOG_PATH}: {exc}') from exc
    data = _mapping(raw, 'catalog')
    targets = tuple(_target(item) for item in _items(data['targets'], 'targets'))
    gates = tuple(_gate(item) for item in _items(data['gates'], 'gates'))
    tiers = tuple(
        TierSpec(
            name=str(row['name']),
            description=str(row['description']),
            failure_policy=str(row['failure_policy']),
            gate_names=tuple(gate.name for gate in gates if str(row['name']) in gate.tiers),
        )
        for value in _items(data['tiers'], 'tiers')
        for row in (_mapping(value, 'tiers[]'),)
    )
    path_rules = tuple(
        PathRule(
            category=str(row['category']),
            patterns=_strings(row['patterns'], 'path_rules.patterns'),
            requires_quality_gate=bool(row['requires_quality_gate']),
            quality_target=str(row['quality_target']) if row.get('quality_target') else None,
            risk_level=str(row['risk']),
            allowed_by_default=bool(row['allowed_by_default']),
        )
        for value in _items(data['path_rules'], 'path_rules')
        for row in (_mapping(value, 'path_rules[]'),)
    )
    return GateCatalog(
        version=str(data['version']),
        gates=gates,
        targets=targets,
        path_rules=path_rules,
        scan_script_smoke_patterns=_strings(
            data['scan_script_smoke_patterns'], 'scan_script_smoke_patterns'
        ),
        tiers=tiers,
    )


CATALOG = _load_catalog()


def _assert_acyclic(graph: dict[str, tuple[str, ...]], label: str) -> None:
    """校验 catalog 小型引用图无环。"""
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        """深度遍历单个 catalog 引用节点；遇到环或未知引用时立即失败。"""
        if node in visiting:
            raise ValueError(f'cycle in {label}: {node}')
        if node in visited:
            return
        visiting.add(node)
        for child in graph[node]:
            if child not in graph:
                raise ValueError(f'unknown reference in {label}: {child}')
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def validate_catalog_schema(catalog: GateCatalog = CATALOG) -> None:
    """校验声明唯一性、引用、能力类型、顺序与 dominance。"""
    gate_names = [gate.name for gate in catalog.gates]
    target_names = [target.name for target in catalog.targets]
    tier_names = [tier.name for tier in catalog.tiers]
    if len(gate_names) != len(set(gate_names)):
        raise ValueError('duplicate Gate name in catalog')
    if len(target_names) != len(set(target_names)):
        raise ValueError('duplicate target name in catalog')
    if len(tier_names) != len(set(tier_names)):
        raise ValueError('duplicate tier name in catalog')
    known_gates, known_targets, known_tiers = set(gate_names), set(target_names), set(tier_names)
    orders: set[tuple[str, int]] = set()
    for gate in catalog.gates:
        if not gate.description.strip() or not gate.description.endswith('。'):
            raise ValueError(f'Gate description must be Chinese prose: {gate.name}')
        if bool(gate.command) == bool(gate.gradle_tasks) or gate.timeout_seconds <= 0:
            raise ValueError(f'Gate execution declaration is invalid: {gate.name}')
        if not gate.target_rules or any(
            rule.target not in known_targets for rule in gate.target_rules
        ):
            raise ValueError(f'Gate target reference is invalid: {gate.name}')
        if any((rule.target, rule.order) in orders for rule in gate.target_rules):
            raise ValueError(f'duplicate Gate target order: {gate.name}')
        orders.update((rule.target, rule.order) for rule in gate.target_rules)
        if not set(gate.tiers) <= known_tiers or not set(gate.included_by) <= known_gates:
            raise ValueError(f'Gate tier/includedBy reference is invalid: {gate.name}')
        if gate.command:
            if gate.command.capability not in {'command', 'playwright', 'cpd', 'scan-smoke'}:
                raise ValueError(f'Gate command capability is invalid: {gate.name}')
            command_targets = {command.target for command in gate.command.target_argv}
            if not command_targets <= set(gate.targets) or (
                command_targets and not gate.command.argv and command_targets != set(gate.targets)
            ):
                raise ValueError(f'Gate target command is invalid: {gate.name}')
        if gate.network_failure not in {'fail', 'blocked'}:
            raise ValueError(f'Gate network failure policy is invalid: {gate.name}')
    if any(
        rule.quality_target not in known_targets
        for rule in catalog.path_rules
        if rule.quality_target
    ):
        raise ValueError('path rule target reference is invalid')
    _assert_acyclic(
        {target.name: target.includes for target in catalog.targets}, 'target dominance'
    )
    _assert_acyclic({gate.name: gate.included_by for gate in catalog.gates}, 'Gate includedBy')


validate_catalog_schema()
CATALOG_VERSION = CATALOG.version
GATES = CATALOG.gates
TARGETS = CATALOG.targets
TIERS = CATALOG.tiers
_GATE_INDEX = {gate.name: gate for gate in GATES}
_TARGET_INDEX = {target.name: target for target in TARGETS}
_TIER_INDEX = {tier.name: tier for tier in TIERS}


def gate_by_name(name: str) -> GateSpec:
    """返回已注册 Gate；未知名称立即失败。"""
    try:
        return _GATE_INDEX[name]
    except KeyError as exc:
        raise ValueError(f'Unknown quality gate: {name}') from exc


def target_by_name(name: str) -> TargetSpec:
    """返回已注册 target；未知名称立即失败。"""
    try:
        return _TARGET_INDEX[name]
    except KeyError as exc:
        raise ValueError(f'Unknown quality target: {name}') from exc


def tier_by_name(name: str) -> TierSpec:
    """返回已注册 tier；未知名称立即失败。"""
    try:
        return _TIER_INDEX[name]
    except KeyError as exc:
        raise ValueError(f'Unknown quality tier: {name}') from exc
