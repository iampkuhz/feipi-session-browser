"""负责从根索引和显式分片加载并校验 Gate catalog。

本模块只把 YAML 转为严格的领域模型，不负责选择或执行 Gate；planner 和 executor 通过这里
暴露的查询入口读取已验证配置。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from scripts.gates.model import (
    ChangedFilesInput,
    GateCatalog,
    GateDefaults,
    GateSpec,
    GateTargetRule,
    MinimumTier,
    OptionalCommandArgs,
    PathRule,
    RunKind,
    RunSpec,
    TargetSpec,
    TargetTrigger,
)

_CATALOG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'gates.yaml'
_ROOT_KEYS = {
    'version',
    'gate_defaults',
    'targets',
    'gate_files',
    'path_rules',
    'target_triggers',
}
_DEFAULT_KEYS = {'minimum_tier', 'timeout', 'changed_files', 'network_failure'}
_FRAGMENT_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\.yaml')
_TIERS = ('quick', 'required', 'full')
_CATALOG_VERSION = 'gate-catalog:v6'


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        """构造无重复键的映射；遇到合并键或重复键立即拒绝配置。"""
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            if key_node.tag == 'tag:yaml.org,2002:merge':
                raise ValueError('YAML merge keys are not supported')
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(
                    f'duplicate YAML mapping key {key!r} at line {key_node.start_mark.line + 1}'
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


# SafeLoader 默认采用 YAML 1.1：yes/on 会变成 bool，012/0x10 会变成 int。
# Catalog 只接受容易人工识别的 YAML 1.2 子集，错误词法会保留为 str，再由 exact-type 校验拒绝。
_UniqueKeyLoader.yaml_implicit_resolvers = {
    first: [
        resolver
        for resolver in resolvers
        if resolver[0] not in {'tag:yaml.org,2002:bool', 'tag:yaml.org,2002:int'}
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_UniqueKeyLoader.add_implicit_resolver(
    'tag:yaml.org,2002:bool', re.compile(r'^(?:true|false)$'), list('tf')
)
_UniqueKeyLoader.add_implicit_resolver(
    'tag:yaml.org,2002:int', re.compile(r'^-?(?:0|[1-9][0-9]*)$'), list('-0123456789')
)


def _load_yaml(path: Path) -> Any:
    try:
        source = path.read_text(encoding='utf-8')
        if any(isinstance(t, (yaml.AnchorToken, yaml.AliasToken)) for t in yaml.scan(source)):
            raise ValueError('YAML anchors and aliases are not supported')
        return yaml.load(source, Loader=_UniqueKeyLoader)
    except (OSError, TypeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f'cannot load {path}: {exc}') from exc


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(type(k) is str for k in value):
        raise ValueError(f'{label} must be a mapping')
    return value


def _items(value: Any, label: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f'{label} must be a sequence')
    if nonempty and not value:
        raise ValueError(f'{label} must not be empty')
    return value


def _string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f'{label} must be a non-empty string')
    return value


def _strings(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    values = _items(value, label, nonempty=nonempty)
    if not all(type(item) is str and item for item in values):
        raise ValueError(f'{label} must contain non-empty strings')
    return tuple(values)


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f'{label} must be a boolean')
    return value


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    if type(value) is not int or (positive and value <= 0) or (not positive and value < 0):
        qualifier = 'positive' if positive else 'non-negative'
        raise ValueError(f'{label} must be a {qualifier} integer')
    return value


def _exact_keys(row: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    actual = set(row)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing or unexpected:
        raise ValueError(f'{label} keys are invalid: missing={missing}, unexpected={unexpected}')


def _enum(value: Any, allowed: tuple[str, ...], label: str) -> str:
    result = _string(value, label)
    if result not in allowed:
        raise ValueError(f'{label} has invalid value: {result}')
    return result


def _gate_file_names(value: Any) -> tuple[str, ...]:
    """读取根索引声明的分片路径，并拒绝重复加载同一分片。"""
    names = _strings(value, 'gate_files', nonempty=True)
    if len(names) != len(set(names)):
        raise ValueError('gate_files must contain unique paths')
    return names


def _gate_fragment_path(catalog_path: Path, relative: str) -> Path:
    """把分片名限制在相邻 gates 目录，避免索引读取目录外文件。"""
    if '\\' in relative or relative.startswith('/'):
        raise ValueError(f'invalid gate fragment path: {relative}')
    parts = relative.split('/')
    if len(parts) != 2 or parts[0] != 'gates' or not _FRAGMENT_NAME.fullmatch(parts[1]):
        raise ValueError(f'invalid gate fragment path: {relative}')
    catalog_directory = catalog_path.parent.resolve()
    gate_directory = (catalog_directory / 'gates').resolve()
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
    """按根索引顺序合并 Gate 分片，并在建模前拒绝重名声明。"""
    gates: list[Any] = []
    owners: dict[str, str] = {}
    for fragment_name in names:
        fragment = _mapping(
            _load_yaml(_gate_fragment_path(catalog_path, fragment_name)), fragment_name
        )
        _exact_keys(fragment, {'gates'}, set(), f'gate fragment {fragment_name}')
        for raw in _items(fragment['gates'], f'gate fragment {fragment_name}.gates', nonempty=True):
            row = _mapping(raw, f'gate fragment {fragment_name}.gates[]')
            name = _string(row.get('name'), f'gate fragment {fragment_name}.gate.name')
            if name in owners:
                raise ValueError(
                    f'duplicate Gate name {name!r} in {fragment_name}; first declared in {owners[name]}'
                )
            owners[name] = fragment_name
            gates.append(row)
    return gates


def _defaults(raw: Any) -> GateDefaults:
    row = _mapping(raw, 'gate_defaults')
    _exact_keys(row, _DEFAULT_KEYS, set(), 'gate_defaults')
    defaults = GateDefaults(
        MinimumTier(_enum(row['minimum_tier'], _TIERS, 'gate_defaults.minimum_tier')),
        _integer(row['timeout'], 'gate_defaults.timeout', positive=True),
        ChangedFilesInput(
            _enum(row['changed_files'], ('none', 'environment'), 'gate_defaults.changed_files')
        ),
        _enum(row['network_failure'], ('fail', 'blocked'), 'gate_defaults.network_failure'),
    )
    expected = GateDefaults(MinimumTier.REQUIRED, 300, ChangedFilesInput.NONE, 'fail')
    if defaults != expected:
        raise ValueError('gate_defaults must equal the catalog v6 contract')
    return defaults


def _target(raw: Any) -> TargetSpec:
    row = _mapping(raw, 'targets[]')
    _exact_keys(row, {'name'}, {'includes'}, 'targets[]')
    return TargetSpec(
        _string(row['name'], 'target.name'),
        _strings(row.get('includes', []), 'target.includes'),
    )


def _optional_args(raw: Any, label: str) -> tuple[OptionalCommandArgs, ...]:
    result = []
    for raw_item in _items(raw, label):
        item = _mapping(raw_item, f'{label}[]')
        _exact_keys(item, {'path', 'argv'}, set(), f'{label}[]')
        result.append(
            OptionalCommandArgs(
                _string(item['path'], f'{label}[].path'),
                _strings(item['argv'], f'{label}[].argv', nonempty=True),
            )
        )
    return tuple(result)


def _command_fields(
    row: dict[str, Any], label: str, *, extras: set[str] | None = None
) -> dict[str, Any]:
    extras = extras or set()
    optional = {'required_paths', 'glob_args', 'optional_args'} | extras
    _exact_keys(row, {'argv'} if 'check' not in extras else {'check'}, optional, label)
    return {
        'argv': _strings(row.get('argv', []), f'{label}.argv', nonempty='check' not in extras),
        'required_paths': _strings(row.get('required_paths', []), f'{label}.required_paths'),
        'glob_args': _strings(row.get('glob_args', []), f'{label}.glob_args'),
        'optional_args': _optional_args(row.get('optional_args', []), f'{label}.optional_args'),
    }


def _run(raw: Any, label: str) -> RunSpec:
    row = _mapping(raw, label)
    if len(row) != 1:
        raise ValueError(f'{label} must contain exactly one discriminated run kind')
    discriminator, body_raw = next(iter(row.items()))
    kind = RunKind(_enum(discriminator, tuple(item.value for item in RunKind), f'{label}.kind'))
    body = _mapping(body_raw, f'{label}.{discriminator}')
    if kind in {RunKind.COMMAND, RunKind.PLAYWRIGHT}:
        return RunSpec(kind=kind, **_command_fields(body, f'{label}.{discriminator}'))
    if kind is RunKind.PYTHON_CHECK:
        run_label = f'{label}.{discriminator}'
        _exact_keys(
            body,
            {'check'},
            {'python', 'args', 'required_paths', 'optional_args'},
            run_label,
        )
        return RunSpec(
            kind=kind,
            check=_string(body['check'], f'{run_label}.check'),
            python=_enum(body.get('python', 'system'), ('system', 'dev'), f'{run_label}.python'),
            args=_strings(body.get('args', []), f'{run_label}.args'),
            required_paths=_strings(body.get('required_paths', []), f'{run_label}.required_paths'),
            optional_args=_optional_args(
                body.get('optional_args', []), f'{run_label}.optional_args'
            ),
        )
    if kind is RunKind.SCAN_SMOKE:
        fields = _command_fields(body, f'{label}.{discriminator}', extras={'prerequisite_tasks'})
        prerequisites = _strings(
            body.get('prerequisite_tasks', []),
            f'{label}.{discriminator}.prerequisite_tasks',
            nonempty=True,
        )
        return RunSpec(kind=kind, prerequisite_tasks=prerequisites, **fields)
    if kind is RunKind.GRADLE_TASK:
        _exact_keys(body, {'tasks'}, {'args'}, f'{label}.gradle-task')
        return RunSpec(
            kind=kind,
            tasks=_strings(body['tasks'], f'{label}.gradle-task.tasks', nonempty=True),
            args=_strings(body.get('args', []), f'{label}.gradle-task.args'),
        )
    _exact_keys(body, {'rules'}, set(), f'{label}.java-rule')
    return RunSpec(
        kind=kind,
        java_rules=_strings(body['rules'], f'{label}.java-rule.rules', nonempty=True),
    )


def _gate(raw: Any, defaults: GateDefaults) -> GateSpec:
    """解析单个 Gate 声明，并阻止重复书写与全局默认值相同的字段。"""
    row = _mapping(raw, 'gates[]')
    optional = _DEFAULT_KEYS
    _exact_keys(row, {'name', 'description', 'targets', 'run'}, optional, 'gates[]')
    for yaml_key, default in (
        ('minimum_tier', defaults.minimum_tier.value),
        ('timeout', defaults.timeout_seconds),
        ('changed_files', defaults.changed_files_input.value),
        ('network_failure', defaults.network_failure),
    ):
        if yaml_key in row and row[yaml_key] == default:
            raise ValueError(
                f'gate.{row.get("name", "?")}.{yaml_key} redundantly overrides gate_defaults'
            )
    rules = []
    for raw_rule in _items(row['targets'], 'gate.targets', nonempty=True):
        rule = _mapping(raw_rule, 'gate.targets[]')
        _exact_keys(rule, {'name', 'order', 'patterns'}, set(), 'gate.targets[]')
        rules.append(
            GateTargetRule(
                _string(rule['name'], 'gate.targets[].name'),
                _integer(rule['order'], 'gate.targets[].order'),
                _strings(rule['patterns'], 'gate.targets[].patterns'),
            )
        )
    return GateSpec(
        name=_string(row['name'], 'gate.name'),
        description=_string(row['description'], 'gate.description'),
        target_rules=tuple(rules),
        run=_run(row['run'], f'gate.{row["name"]}.run'),
        minimum_tier=MinimumTier(
            _enum(row.get('minimum_tier', defaults.minimum_tier.value), _TIERS, 'gate.minimum_tier')
        ),
        timeout_seconds=_integer(
            row.get('timeout', defaults.timeout_seconds), 'gate.timeout', positive=True
        ),
        changed_files_input=ChangedFilesInput(
            _enum(
                row.get('changed_files', defaults.changed_files_input.value),
                ('none', 'environment'),
                'gate.changed_files',
            )
        ),
        network_failure=_enum(
            row.get('network_failure', defaults.network_failure),
            ('fail', 'blocked'),
            'gate.network_failure',
        ),
    )


def _path_rule(raw: Any) -> PathRule:
    row = _mapping(raw, 'path_rules[]')
    _exact_keys(row, {'category', 'patterns', 'risk'}, {'targets', 'allowed'}, 'path_rules[]')
    return PathRule(
        _string(row['category'], 'path_rule.category'),
        _strings(row['patterns'], 'path_rule.patterns', nonempty=True),
        _strings(row.get('targets', []), 'path_rule.targets'),
        _enum(row['risk'], ('low', 'medium', 'high', 'local'), 'path_rule.risk'),
        _boolean(row.get('allowed', True), 'path_rule.allowed'),
    )


def _target_trigger(raw: Any) -> TargetTrigger:
    row = _mapping(raw, 'target_triggers[]')
    _exact_keys(row, {'target', 'patterns'}, set(), 'target_triggers[]')
    return TargetTrigger(
        _string(row['target'], 'target_triggers[].target'),
        _strings(row['patterns'], 'target_triggers[].patterns', nonempty=True),
    )


def _load_catalog(path: Path = _CATALOG_PATH) -> GateCatalog:
    data = _mapping(_load_yaml(path), 'catalog')
    _exact_keys(data, _ROOT_KEYS, set(), 'catalog')
    version = _string(data['version'], 'catalog.version')
    if version != _CATALOG_VERSION:
        raise ValueError(f'catalog.version must be {_CATALOG_VERSION!r}')
    defaults = _defaults(data['gate_defaults'])
    names = _gate_file_names(data['gate_files'])
    catalog = GateCatalog(
        version=version,
        gate_defaults=defaults,
        gates=tuple(_gate(item, defaults) for item in _load_gates(path, names)),
        targets=tuple(_target(item) for item in _items(data['targets'], 'targets', nonempty=True)),
        path_rules=tuple(
            _path_rule(item) for item in _items(data['path_rules'], 'path_rules', nonempty=True)
        ),
        target_triggers=tuple(
            _target_trigger(raw) for raw in _items(data['target_triggers'], 'target_triggers')
        ),
    )
    validate_catalog_schema(catalog)
    return catalog


def _assert_acyclic(graph: dict[str, tuple[str, ...]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        """深度遍历一个目标节点，同时报告环和未知引用。"""
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


def validate_catalog_schema(catalog: GateCatalog) -> None:
    """校验跨分片的名称、目标、顺序和 Java 规则等全局唯一约束。"""
    gate_names = [gate.name for gate in catalog.gates]
    target_names = [target.name for target in catalog.targets]
    if len(gate_names) != len(set(gate_names)):
        raise ValueError('duplicate Gate name in catalog')
    if len(target_names) != len(set(target_names)):
        raise ValueError('duplicate target name in catalog')
    known_targets = set(target_names)
    orders: set[tuple[str, int]] = set()
    java_rules: set[str] = set()
    for gate in catalog.gates:
        if not gate.description.endswith('。'):
            raise ValueError(f'Gate description must be Chinese prose: {gate.name}')
        if any(rule.target not in known_targets for rule in gate.target_rules):
            raise ValueError(f'Gate target reference is invalid: {gate.name}')
        if len(gate.targets) != len(set(gate.targets)):
            raise ValueError(f'duplicate Gate target: {gate.name}')
        if any((rule.target, rule.order) in orders for rule in gate.target_rules):
            raise ValueError(f'duplicate Gate target order: {gate.name}')
        orders.update((rule.target, rule.order) for rule in gate.target_rules)
        if java_rules.intersection(gate.run.java_rules):
            raise ValueError(f'duplicate Java quality rule: {gate.name}')
        java_rules.update(gate.run.java_rules)
    for target in catalog.targets:
        if len(target.includes) != len(set(target.includes)):
            raise ValueError(f'duplicate target dominance: {target.name}')
    if any(target not in known_targets for rule in catalog.path_rules for target in rule.targets):
        raise ValueError('path rule target reference is invalid')
    if any(trigger.target not in known_targets for trigger in catalog.target_triggers):
        raise ValueError('target trigger reference is invalid')
    _assert_acyclic(
        {target.name: target.includes for target in catalog.targets}, 'target dominance'
    )


CATALOG = _load_catalog()
CATALOG_VERSION = CATALOG.version
GATES = CATALOG.gates
TARGETS = CATALOG.targets
_GATE_INDEX = {gate.name: gate for gate in GATES}
_TARGET_INDEX = {target.name: target for target in TARGETS}


def gate_by_name(name: str) -> GateSpec:
    """按名称返回已验证 Gate，供 planner 构造执行计划。"""
    try:
        return _GATE_INDEX[name]
    except KeyError as exc:
        raise ValueError(f'Unknown quality gate: {name}') from exc


def target_by_name(name: str) -> TargetSpec:
    """按名称返回已验证目标，供 planner 展开目标包含关系。"""
    try:
        return _TARGET_INDEX[name]
    except KeyError as exc:
        raise ValueError(f'Unknown quality target: {name}') from exc


def tier_by_name(name: str) -> str:
    """验证并返回层级名称，供 CLI 在规划前拒绝未知层级。"""
    return _enum(name, _TIERS, 'tier')
