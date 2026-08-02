"""负责从唯一根索引及其显式业务分片加载并校验 typed Gate catalog；不负责规划或执行 Gate。"""

from __future__ import annotations

import re
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
    TargetCommand,
    TargetSpec,
    TierSpec,
)

_CATALOG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'gates.yaml'
_ROOT_KEYS = {
    'version',
    'targets',
    'gate_files',
    'path_rules',
    'scan_script_smoke_patterns',
    'tiers',
}
_FRAGMENT_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\.yaml')


class _UniqueKeyLoader(yaml.SafeLoader):
    """加载受信任 schema，同时拒绝 YAML 默认会静默覆盖的重复 key。"""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        """逐项构造 mapping，并在重复 key 或 merge key 处立即失败。"""
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            if key_node.tag == 'tag:yaml.org,2002:merge':
                raise ValueError('YAML merge keys are not supported')
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                mark = key_node.start_mark
                raise ValueError(f'duplicate YAML mapping key {key!r} at line {mark.line + 1}')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _load_yaml(path: Path) -> Any:
    """读取一份 YAML；拒绝 anchor/alias，避免声明通过隐式继承变得不可读。"""
    try:
        source = path.read_text(encoding='utf-8')
        if any(
            isinstance(token, (yaml.AnchorToken, yaml.AliasToken)) for token in yaml.scan(source)
        ):
            raise ValueError('YAML anchors and aliases are not supported')
        return yaml.load(source, Loader=_UniqueKeyLoader)
    except (OSError, TypeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f'cannot load {path}: {exc}') from exc


def _exact_keys(row: dict[str, Any], expected: set[str], label: str) -> None:
    """要求声明只包含给定 key，防止拼写错误或旧格式被静默忽略。"""
    actual = set(row)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f'{label} keys are invalid: missing={missing}, unexpected={unexpected}')


def _gate_file_names(value: Any) -> tuple[str, ...]:
    """校验根索引中的显式分片清单及其稳定顺序。"""
    names = _strings(value, 'gate_files')
    if not names:
        raise ValueError('gate_files must not be empty')
    if len(names) != len(set(names)):
        raise ValueError('gate_files must contain unique paths')
    return names


def _gate_fragment_path(catalog_path: Path, relative: str) -> Path:
    """把受限 include 解析为根旁 ``gates/`` 下的 repo-local YAML 文件。"""
    if '\\' in relative or relative.startswith('/'):
        raise ValueError(f'invalid gate fragment path: {relative}')
    parts = relative.split('/')
    if (
        len(parts) != 2
        or parts[0] != 'gates'
        or parts[1] in {'', '.', '..'}
        or not _FRAGMENT_NAME.fullmatch(parts[1])
    ):
        raise ValueError(f'invalid gate fragment path: {relative}')

    catalog_directory = catalog_path.parent.resolve()
    gate_directory = (catalog_directory / 'gates').resolve()
    if not gate_directory.is_relative_to(catalog_directory):
        raise ValueError('gate fragment directory escapes catalog directory')
    candidate = catalog_path.parent / relative
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f'cannot load gate fragment {relative}: {exc}') from exc
    if not resolved.is_relative_to(gate_directory):
        raise ValueError(f'gate fragment escapes gates directory: {relative}')
    if not resolved.is_file():
        raise ValueError(f'gate fragment is not a file: {relative}')
    return resolved


def _load_gates(catalog_path: Path, names: tuple[str, ...]) -> list[Any]:
    """聚合业务分片，并按每条声明唯一的 ``catalog_order`` 恢复稳定顺序。"""
    gates: list[tuple[int, dict[str, Any]]] = []
    owners: dict[str, str] = {}
    order_owners: dict[int, str] = {}
    for name in names:
        fragment_path = _gate_fragment_path(catalog_path, name)
        fragment = _mapping(_load_yaml(fragment_path), f'gate fragment {name}')
        _exact_keys(fragment, {'gates'}, f'gate fragment {name}')
        fragment_gates = _items(fragment['gates'], f'gate fragment {name}.gates')
        if not fragment_gates:
            raise ValueError(f'gate fragment {name}.gates must not be empty')
        for item in fragment_gates:
            row = _mapping(item, f'gate fragment {name}.gates[]')
            gate_name = row.get('name')
            if not isinstance(gate_name, str) or not gate_name:
                raise ValueError(f'Gate name must be a non-empty string in {name}')
            if gate_name in owners:
                raise ValueError(
                    f'duplicate Gate name {gate_name!r} in {name}; first declared in '
                    f'{owners[gate_name]}'
                )
            owners[gate_name] = name
            order = row.get('catalog_order')
            if isinstance(order, bool) or not isinstance(order, int) or order < 0:
                raise ValueError(
                    f'Gate catalog_order must be a non-negative integer in {name}: {gate_name}'
                )
            if order in order_owners:
                raise ValueError(
                    f'duplicate Gate catalog_order {order} in {name}; first declared in '
                    f'{order_owners[order]}'
                )
            order_owners[order] = name
            declaration = dict(row)
            declaration.pop('catalog_order')
            gates.append((order, declaration))

    return [declaration for _, declaration in sorted(gates, key=lambda item: item[0])]


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
        prerequisite_tasks=_strings(
            row.get('prerequisite_tasks', []), f'{label}.prerequisite_tasks'
        ),
        existing_only=bool(row.get('existing_only', False)),
    )


def _target(raw: Any) -> TargetSpec:
    """加载单条 target 声明。"""
    row = _mapping(raw, 'targets[]')
    return TargetSpec(
        name=str(row['name']),
        includes=_strings(row.get('includes', []), 'target.includes'),
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
        java_rules=_strings(gradle.get('java_rules', []), 'gate.gradle.java_rules'),
        timeout_seconds=int(row['timeout']),
        incremental_mode=IncrementalMode(str(row['incremental'])),
        changed_files_input=ChangedFilesInput(str(row['changed_files'])),
        included_by=_strings(row.get('included_by', []), 'gate.included_by'),
        tiers=_strings(row['tiers'], 'gate.tiers'),
        description=str(row['description']),
        network_failure=str(row.get('network_failure', 'fail')),
    )


def _load_catalog(path: Path = _CATALOG_PATH) -> GateCatalog:
    """读取根索引及显式有序分片，校验 schema 并构造不可变模型。"""
    raw = _load_yaml(path)
    data = _mapping(raw, 'catalog')
    _exact_keys(data, _ROOT_KEYS, 'catalog')
    gate_files = _gate_file_names(data['gate_files'])
    targets = tuple(_target(item) for item in _items(data['targets'], 'targets'))
    gates = tuple(_gate(item) for item in _load_gates(path, gate_files))
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
    java_rules: set[str] = set()
    for gate in catalog.gates:
        if not gate.description.strip() or not gate.description.endswith('。'):
            raise ValueError(f'Gate description must be Chinese prose: {gate.name}')
        if bool(gate.command) == bool(gate.gradle_tasks) or gate.timeout_seconds <= 0:
            raise ValueError(f'Gate execution declaration is invalid: {gate.name}')
        if len(gate.java_rules) != len(set(gate.java_rules)) or java_rules.intersection(
            gate.java_rules
        ):
            raise ValueError(f'duplicate Java quality rule: {gate.name}')
        java_rules.update(gate.java_rules)
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
            if gate.command.capability not in {'command', 'playwright', 'scan-smoke'}:
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
