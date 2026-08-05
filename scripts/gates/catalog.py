"""严格加载当前唯一的双模式 Gate Catalog。

Catalog 只接受 OpenSpec 定义的当前格式。旧 tier、默认值、Target rule 与其他未知字段会直接
导致整个 Catalog 加载失败，不提供兼容解析路径。本模块不负责选择或执行 Gate；Planner
与 Executor 分别调用这里暴露的只读声明完成后续工作。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from scripts.gates.model import (
    GateCatalog,
    GateSpec,
    GateTrigger,
    PathRule,
    RunKind,
    RunProfile,
    RunSpec,
    TargetSpec,
    TriggerMode,
)

_CATALOG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'gates.yaml'
_ROOT_KEYS = {'targets', 'gate_files', 'path_rules'}
_FRAGMENT_NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\.yaml')
_IDENTIFIER = re.compile(r'[a-z][A-Za-z0-9]*')
_TARGET_IDENTIFIER = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*')
_CHECK_IDENTIFIER = re.compile(r'[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*')
_CHINESE_CHARACTER = re.compile(r'[\u4e00-\u9fff]')
_COMMON_PROFILE_KEYS = {'target_seconds', 'timeout_seconds'}
_PROFILE_FIELDS: dict[RunKind, tuple[set[str], set[str]]] = {
    RunKind.COMMAND: ({'argv'}, {'required_paths', 'append_globs'}),
    RunKind.PYTHON_CHECK: ({'id'}, {'runtime', 'args'}),
    RunKind.GRADLE_TASK: ({'tasks'}, {'args'}),
    RunKind.JAVA_RULE: ({'rules'}, set()),
    RunKind.PLAYWRIGHT: ({'tests'}, {'args'}),
    RunKind.SCAN_SMOKE: ({'tests', 'prerequisite_tasks'}, {'args'}),
}


class _UniqueKeyLoader(yaml.SafeLoader):
    """拒绝 YAML 重复键和 merge key，避免配置被静默覆盖。"""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        """构造单个 YAML 映射，并在重复键或合并键出现时立即拒绝配置。"""

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


# 只接受容易人工识别的 YAML 1.2 bool/int 词法，避免 yes、012 等值被隐式改型。
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
        if any(
            isinstance(token, (yaml.AnchorToken, yaml.AliasToken)) for token in yaml.scan(source)
        ):
            raise ValueError('YAML anchors and aliases are not supported')
        return yaml.load(source, Loader=_UniqueKeyLoader)
    except (OSError, TypeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f'cannot load {path}: {exc}') from exc


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(type(key) is str for key in value):
        raise ValueError(f'{label} must be a mapping')
    return value


def _items(value: Any, label: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = ' a non-empty sequence' if nonempty else ' a sequence'
        raise ValueError(f'{label} must be{suffix}')
    return value


def _string(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or '\n' in value:
        raise ValueError(f'{label} must be a non-empty single-line string')
    return value


def _identifier(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    result = _string(value, label)
    if not pattern.fullmatch(result):
        raise ValueError(f'{label} has invalid identifier: {result}')
    return result


def _description(value: Any, label: str) -> str:
    """读取便于中文维护者理解的单句说明。"""

    result = _string(value, label)
    if not result.endswith('。') or not _CHINESE_CHARACTER.search(result):
        raise ValueError(f'{label} must be one Chinese sentence ending with 。')
    return result


def _enum(value: Any, allowed: tuple[str, ...], label: str) -> str:
    """读取一个明确枚举值，拒绝大小写或别名兼容。"""

    result = _string(value, label)
    if result not in allowed:
        raise ValueError(f'{label} has invalid value: {result}')
    return result


def _strings(value: Any, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    values = _items(value, label, nonempty=nonempty)
    return tuple(_string(item, f'{label}[]') for item in values)


def _positive_integer(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f'{label} must be a positive integer')
    return value


def _exact_keys(row: dict[str, Any], required: set[str], optional: set[str], label: str) -> None:
    missing = sorted(required - set(row))
    unexpected = sorted(set(row) - required - optional)
    if missing or unexpected:
        raise ValueError(f'{label} keys are invalid: missing={missing}, unexpected={unexpected}')


def _repo_globs(value: Any, label: str) -> tuple[str, ...]:
    globs = _strings(value, label, nonempty=True)
    if len(globs) != len(set(globs)):
        raise ValueError(f'{label} must not contain duplicates')
    if any(
        glob.startswith(('/', './'))
        or '\\' in glob
        or any(part == '..' for part in glob.split('/'))
        for glob in globs
    ):
        raise ValueError(f'{label} must contain normalized repository-relative globs')
    return globs


def _repo_paths(value: Any, label: str) -> tuple[str, ...]:
    """读取不含通配符的规范化仓库相对路径。"""

    paths = _strings(value, label)
    if len(paths) != len(set(paths)) or any(
        path.startswith(('/', './'))
        or '\\' in path
        or any(part == '..' for part in path.split('/'))
        or any(character in path for character in '*?[]')
        for path in paths
    ):
        raise ValueError(f'{label} must contain unique normalized repository-relative paths')
    return paths


def _gate_file_names(value: Any) -> tuple[str, ...]:
    """校验并返回 Catalog 显式登记的唯一 Gate 分片路径。"""

    names = _strings(value, 'gate_files', nonempty=True)
    if len(names) != len(set(names)):
        raise ValueError('gate_files must not contain duplicates')
    if any(
        len(parts := name.split('/')) != 2
        or parts[0] != 'gates'
        or not _FRAGMENT_NAME.fullmatch(parts[1])
        for name in names
    ):
        raise ValueError('gate_files must contain canonical gates/<name>.yaml paths')
    return names


def _gate_fragment_path(catalog_path: Path, relative: str) -> Path:
    """解析已登记分片，并阻止路径越出 Catalog 的 gates 目录。"""

    gate_directory = (catalog_path.parent / 'gates').resolve()
    try:
        resolved = (catalog_path.parent / relative).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f'cannot load gate fragment {relative}: {exc}') from exc
    if not resolved.is_relative_to(gate_directory) or not resolved.is_file():
        raise ValueError(f'gate fragment escapes gates directory: {relative}')
    return resolved


def _target(raw: Any) -> TargetSpec:
    row = _mapping(raw, 'targets[]')
    _exact_keys(row, {'name', 'description'}, set(), 'targets[]')
    return TargetSpec(
        _identifier(row['name'], 'target.name', _TARGET_IDENTIFIER),
        _description(row['description'], 'target.description'),
    )


def _path_rule(raw: Any) -> PathRule:
    row = _mapping(raw, 'path_rules[]')
    _exact_keys(row, {'category', 'patterns', 'risk'}, {'allowed'}, 'path_rules[]')
    allowed = row.get('allowed', True)
    if type(allowed) is not bool:
        raise ValueError('path_rule.allowed must be a boolean')
    return PathRule(
        _string(row['category'], 'path_rule.category'),
        _repo_globs(row['patterns'], 'path_rule.patterns'),
        _enum(row['risk'], ('low', 'medium', 'high', 'local'), 'path_rule.risk'),
        allowed,
    )


def _trigger(raw: Any, label: str) -> GateTrigger:
    row = _mapping(raw, label)
    mode = TriggerMode(_string(row.get('mode'), f'{label}.mode'))
    if mode is TriggerMode.ALWAYS:
        _exact_keys(row, {'mode'}, set(), label)
        return GateTrigger(mode)
    _exact_keys(row, {'mode', 'paths'}, set(), label)
    return GateTrigger(mode, _repo_globs(row['paths'], f'{label}.paths'))


def _profile_values(kind: RunKind, row: dict[str, Any], label: str) -> dict[str, Any]:
    required, optional = _PROFILE_FIELDS[kind]
    _exact_keys(row, _COMMON_PROFILE_KEYS | required, optional, label)
    target_seconds = _positive_integer(row['target_seconds'], f'{label}.target_seconds')
    timeout_seconds = _positive_integer(row['timeout_seconds'], f'{label}.timeout_seconds')
    if timeout_seconds < target_seconds:
        raise ValueError(f'{label}.timeout_seconds must be >= target_seconds')

    values: dict[str, Any] = {
        'target_seconds': target_seconds,
        'timeout_seconds': timeout_seconds,
    }
    if kind is RunKind.COMMAND:
        values.update(
            argv=_strings(row['argv'], f'{label}.argv', nonempty=True),
            required_paths=_repo_paths(row.get('required_paths', []), f'{label}.required_paths'),
            append_globs=(
                _repo_globs(row['append_globs'], f'{label}.append_globs')
                if 'append_globs' in row
                else ()
            ),
        )
    elif kind is RunKind.PYTHON_CHECK:
        values.update(
            check_id=_identifier(row['id'], f'{label}.id', _CHECK_IDENTIFIER),
            runtime=_string(row.get('runtime', 'system'), f'{label}.runtime'),
            args=_strings(row.get('args', []), f'{label}.args'),
        )
        if values['runtime'] not in {'system', 'dev'}:
            raise ValueError(f'{label}.runtime has invalid value: {values["runtime"]}')
    elif kind is RunKind.GRADLE_TASK:
        values.update(
            tasks=_strings(row['tasks'], f'{label}.tasks', nonempty=True),
            args=_strings(row.get('args', []), f'{label}.args'),
        )
    elif kind is RunKind.JAVA_RULE:
        values['rules'] = _strings(row['rules'], f'{label}.rules', nonempty=True)
    elif kind is RunKind.PLAYWRIGHT:
        values.update(
            tests=_strings(row['tests'], f'{label}.tests', nonempty=True),
            args=_strings(row.get('args', []), f'{label}.args'),
        )
    else:
        values.update(
            tests=_strings(row['tests'], f'{label}.tests', nonempty=True),
            prerequisite_tasks=_strings(
                row['prerequisite_tasks'], f'{label}.prerequisite_tasks', nonempty=True
            ),
            args=_strings(row.get('args', []), f'{label}.args'),
        )
    return values


def _profile(kind: RunKind, raw: Any, label: str, incremental: RunProfile | None) -> RunProfile:
    row = _mapping(raw, label)
    if 'same_as' not in row:
        return RunProfile(**_profile_values(kind, row, label))
    if incremental is None:
        raise ValueError(f'{label}.same_as is only allowed for full profile')
    _exact_keys(row, {'same_as', 'target_seconds', 'timeout_seconds'}, set(), label)
    if row['same_as'] != 'incremental':
        raise ValueError(f'{label}.same_as must equal incremental')
    target_seconds = _positive_integer(row['target_seconds'], f'{label}.target_seconds')
    timeout_seconds = _positive_integer(row['timeout_seconds'], f'{label}.timeout_seconds')
    if timeout_seconds < target_seconds:
        raise ValueError(f'{label}.timeout_seconds must be >= target_seconds')
    values = {
        field: getattr(incremental, field)
        for field in RunProfile.__dataclass_fields__
        if field not in {'target_seconds', 'timeout_seconds'}
    }
    return RunProfile(target_seconds, timeout_seconds, **values)


def _run(raw: Any, label: str) -> RunSpec:
    row = _mapping(raw, label)
    _exact_keys(row, {'kind', 'incremental', 'full'}, set(), label)
    try:
        kind = RunKind(_string(row['kind'], f'{label}.kind'))
    except ValueError as exc:
        raise ValueError(f'{label}.kind has invalid value: {row.get("kind")}') from exc
    incremental = _profile(kind, row['incremental'], f'{label}.incremental', None)
    full = _profile(kind, row['full'], f'{label}.full', incremental)
    return RunSpec(kind, incremental, full)


def _gate(raw: Any) -> GateSpec:
    """把一条严格五字段声明解析成不可变 Gate 规格。"""

    row = _mapping(raw, 'gates[]')
    _exact_keys(row, {'name', 'description', 'trigger', 'run'}, {'targets'}, 'gates[]')
    name = _identifier(row['name'], 'gate.name', _IDENTIFIER)
    targets = _strings(row.get('targets', []), f'gate.{name}.targets')
    if len(targets) != len(set(targets)):
        raise ValueError(f'gate.{name}.targets must not contain duplicates')
    if any(not _TARGET_IDENTIFIER.fullmatch(target) for target in targets):
        raise ValueError(f'gate.{name}.targets contains invalid Target identifier')
    return GateSpec(
        name,
        _description(row['description'], f'gate.{name}.description'),
        _trigger(row['trigger'], f'gate.{name}.trigger'),
        targets,
        _run(row['run'], f'gate.{name}.run'),
    )


def _load_gates(catalog_path: Path, names: tuple[str, ...]) -> tuple[GateSpec, ...]:
    """按登记顺序加载 Gate 分片，并拒绝跨分片的重名声明。"""

    result: list[GateSpec] = []
    owners: dict[str, str] = {}
    for fragment_name in names:
        fragment = _mapping(
            _load_yaml(_gate_fragment_path(catalog_path, fragment_name)), fragment_name
        )
        _exact_keys(fragment, {'gates'}, set(), f'gate fragment {fragment_name}')
        for raw in _items(fragment['gates'], f'{fragment_name}.gates', nonempty=True):
            gate = _gate(raw)
            if gate.name in owners:
                raise ValueError(
                    f'duplicate Gate name {gate.name!r} in {fragment_name}; '
                    f'first declared in {owners[gate.name]}'
                )
            owners[gate.name] = fragment_name
            result.append(gate)
    return tuple(result)


def validate_catalog_schema(catalog: GateCatalog) -> None:
    """校验跨声明引用和必须全局唯一的 owner。"""

    target_names = tuple(target.name for target in catalog.targets)
    if len(target_names) != len(set(target_names)):
        raise ValueError('target names must be unique')
    known_targets = set(target_names)
    unknown = sorted(
        {target for gate in catalog.gates for target in gate.targets if target not in known_targets}
    )
    if unknown:
        raise ValueError(f'unknown Gate target references: {unknown}')
    empty_targets = sorted(
        target
        for target in known_targets
        if not any(target in gate.targets for gate in catalog.gates)
    )
    if empty_targets:
        raise ValueError(f'Target selects no Gate: {empty_targets}')

    java_rules: set[str] = set()
    for gate in catalog.gates:
        overlap = java_rules.intersection(gate.run.incremental.rules, gate.run.full.rules)
        # 同一个 Gate 的两个 profile 可以拥有相同 rule；不同 Gate 不可重复拥有。
        owned = set(gate.run.incremental.rules) | set(gate.run.full.rules)
        if overlap and gate.run.incremental.rules != gate.run.full.rules:
            raise ValueError(f'Gate {gate.name} has inconsistent Java rule ownership')
        duplicate_owner = java_rules.intersection(owned)
        if duplicate_owner:
            raise ValueError(f'duplicate Java rule ownership: {sorted(duplicate_owner)}')
        java_rules.update(owned)


def _load_catalog(path: Path) -> GateCatalog:
    data = _mapping(_load_yaml(path), 'catalog')
    _exact_keys(data, _ROOT_KEYS, set(), 'catalog')
    targets = tuple(_target(raw) for raw in _items(data['targets'], 'targets', nonempty=True))
    gates = _load_gates(path, _gate_file_names(data['gate_files']))
    path_rules = tuple(
        _path_rule(raw) for raw in _items(data['path_rules'], 'path_rules', nonempty=True)
    )
    catalog = GateCatalog(targets, gates, path_rules)
    validate_catalog_schema(catalog)
    return catalog


CATALOG = _load_catalog(_CATALOG_PATH)
GATES = CATALOG.gates
TARGETS = CATALOG.targets


def gate_by_name(name: str) -> GateSpec:
    """按唯一名称查找 Gate。"""

    for gate in GATES:
        if gate.name == name:
            return gate
    return _raise_unknown('Gate', name)


def target_by_name(name: str) -> TargetSpec:
    """按唯一名称查找人工 Target preset。"""

    for target in TARGETS:
        if target.name == name:
            return target
    return _raise_unknown('Target', name)


def _raise_unknown(kind: str, name: str) -> Any:
    raise ValueError(f'Unknown quality {kind.lower()}: {name}')
