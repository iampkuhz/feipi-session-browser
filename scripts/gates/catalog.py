"""校验并查询集中在 Python 中的 Gate Catalog。

机器声明只存在于 :mod:`scripts.gates.definitions`。本模块不再解析 YAML，也不负责
选择或执行 Gate；这里只保护跨声明引用和每种 typed recipe 的最小不变量。
"""

from __future__ import annotations

import re
from typing import Never

from scripts.gates.definitions import CATALOG, GATES, TARGETS
from scripts.gates.model import GateCatalog, GateSpec, RunKind, RunStep, TargetSpec, TriggerMode

_GATE_ID = re.compile(r'[a-z][A-Za-z0-9]*')
_TARGET_ID = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*')
_CHECK_ID = re.compile(r'[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*')
_CHINESE = re.compile(r'[\u4e00-\u9fff]')


def _unique(values: tuple[str, ...], label: str) -> None:
    """拒绝空值或重复值，避免声明被后写项静默覆盖。"""

    if any(not value or value != value.strip() for value in values):
        raise ValueError(f'{label} must contain non-empty trimmed strings')
    if len(values) != len(set(values)):
        raise ValueError(f'{label} must not contain duplicates')


def _description(value: str, label: str) -> None:
    """保证面向中文维护者的说明是一句完整中文。"""

    if not value.endswith('。') or not _CHINESE.search(value) or '\n' in value:
        raise ValueError(f'{label} must be one Chinese sentence ending with 。')


def _repo_paths(paths: tuple[str, ...], label: str, *, allow_glob: bool) -> None:
    """校验 repository-relative path/glob，不接受绝对路径或上跳。"""

    _unique(paths, label)
    for path in paths:
        if (
            path.startswith(('/', './'))
            or '\\' in path
            or any(part == '..' for part in path.split('/'))
            or (not allow_glob and any(character in path for character in '*?[]'))
        ):
            raise ValueError(f'{label} contains invalid repository path: {path}')


def _unused_fields(step: RunStep, allowed: set[str]) -> list[str]:
    """返回当前 adapter 不应携带但实际有值的 recipe 字段。"""

    values = {
        'argv': step.argv,
        'required_paths': step.required_paths,
        'append_globs': step.append_globs,
        'check_id': step.check_id,
        'runtime': step.runtime if step.runtime != 'system' else None,
        'args': step.args,
        'tasks': step.tasks,
        'rules': step.rules,
        'tests': step.tests,
        'prerequisite_tasks': step.prerequisite_tasks,
    }
    return sorted(name for name, value in values.items() if value and name not in allowed)


def _validate_step(step: RunStep, label: str) -> None:
    """验证一个 leaf 与其 adapter 的字段严格匹配。"""

    if not _GATE_ID.fullmatch(step.name):
        raise ValueError(f'{label}.name has invalid identifier: {step.name}')

    allowed: set[str]
    if step.kind is RunKind.COMMAND:
        allowed = {'argv', 'required_paths', 'append_globs'}
        if not step.argv:
            raise ValueError(f'{label}.argv must not be empty')
        _repo_paths(step.required_paths, f'{label}.required_paths', allow_glob=False)
        _repo_paths(step.append_globs, f'{label}.append_globs', allow_glob=True)
    elif step.kind is RunKind.PYTHON_CHECK:
        allowed = {'check_id', 'runtime', 'args'}
        if not step.check_id or not _CHECK_ID.fullmatch(step.check_id):
            raise ValueError(f'{label}.check_id has invalid identifier')
        if step.runtime not in {'system', 'dev'}:
            raise ValueError(f'{label}.runtime has invalid value: {step.runtime}')
    elif step.kind is RunKind.GRADLE_TASK:
        allowed = {'tasks', 'args'}
        if len(step.tasks) != 1:
            raise ValueError(f'{label}.tasks must contain exactly one item')
    elif step.kind is RunKind.JAVA_RULE:
        allowed = {'rules'}
        if len(step.rules) != 1:
            raise ValueError(f'{label}.rules must contain exactly one item')
    elif step.kind is RunKind.PLAYWRIGHT:
        allowed = {'tests', 'args'}
        if not step.tests:
            raise ValueError(f'{label}.tests must not be empty')
    elif step.kind is RunKind.SCAN_SMOKE:
        allowed = {'tests', 'prerequisite_tasks', 'args'}
        if not step.tests or not step.prerequisite_tasks:
            raise ValueError(f'{label} requires tests and prerequisite_tasks')
    else:  # pragma: no cover - enum 扩展必须先显式增加 adapter 校验。
        raise ValueError(f'{label}.kind is unsupported: {step.kind}')

    unexpected = _unused_fields(step, allowed)
    if unexpected:
        raise ValueError(f'{label} contains fields unused by {step.kind.value}: {unexpected}')


def validate_catalog_schema(catalog: GateCatalog) -> None:
    """校验当前 typed declaration 的全局引用与 recipe 不变量。"""

    target_names = tuple(target.name for target in catalog.targets)
    gate_names = tuple(gate.name for gate in catalog.gates)
    _unique(target_names, 'Target names')
    _unique(gate_names, 'Gate names')
    if any(not _TARGET_ID.fullmatch(name) for name in target_names):
        raise ValueError('Target name has invalid identifier')
    if any(not _GATE_ID.fullmatch(name) for name in gate_names):
        raise ValueError('Gate name has invalid identifier')
    for target in catalog.targets:
        _description(target.description, f'Target {target.name}.description')

    known_targets = set(target_names)
    referenced_targets: set[str] = set()
    java_rule_owners: set[str] = set()
    for gate in catalog.gates:
        _description(gate.description, f'Gate {gate.name}.description')
        _unique(gate.targets, f'Gate {gate.name}.targets')
        unknown = sorted(set(gate.targets) - known_targets)
        if unknown:
            raise ValueError(f'Gate {gate.name} references unknown Targets: {unknown}')
        referenced_targets.update(gate.targets)

        if gate.trigger.mode is TriggerMode.ALWAYS:
            if gate.trigger.paths:
                raise ValueError(f'Gate {gate.name} always trigger cannot contain paths')
        elif gate.trigger.mode is TriggerMode.CHANGED:
            if not gate.trigger.paths:
                raise ValueError(f'Gate {gate.name} changed trigger requires paths')
            _repo_paths(gate.trigger.paths, f'Gate {gate.name}.trigger.paths', allow_glob=True)

        targets = gate.run.target_seconds
        if type(targets.incremental) is not int or targets.incremental <= 0:
            raise ValueError(f'Gate {gate.name} incremental target must be a positive integer')
        if type(targets.full) is not int or targets.full <= 0:
            raise ValueError(f'Gate {gate.name} full target must be a positive integer')
        if not gate.run.steps:
            raise ValueError(f'Gate {gate.name} recipe must contain at least one leaf')
        step_names = tuple(step.name for step in gate.run.steps)
        _unique(step_names, f'Gate {gate.name}.leaf names')
        for index, step in enumerate(gate.run.steps):
            _validate_step(step, f'Gate {gate.name}.steps[{index}]')
            for rule in step.rules:
                if rule in java_rule_owners:
                    raise ValueError(f'duplicate Java rule ownership: {rule}')
                java_rule_owners.add(rule)

    empty_targets = sorted(known_targets - referenced_targets)
    if empty_targets:
        raise ValueError(f'Target selects no Gate: {empty_targets}')


def gate_by_name(name: str) -> GateSpec:
    """按唯一名称查找 Gate，未知名称直接拒绝。"""

    for gate in GATES:
        if gate.name == name:
            return gate
    return _unknown('Gate', name)


def target_by_name(name: str) -> TargetSpec:
    """按唯一名称查找人工 Target preset，未知名称直接拒绝。"""

    for target in TARGETS:
        if target.name == name:
            return target
    return _unknown('Target', name)


def _unknown(kind: str, name: str) -> Never:
    raise ValueError(f'Unknown quality {kind.lower()}: {name}')


validate_catalog_schema(CATALOG)
