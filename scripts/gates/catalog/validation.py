"""负责校验 Catalog 声明、跨引用与 RecipeStep owner 不变量；不负责运行命令。

由 registry 初始化、测试和 Maintenance 健康审计调用。"""

from __future__ import annotations

import re

from scripts.gates.catalog.gate_contracts import (
    GateCatalog,
    RecipeStep,
    RecipeStepKind,
    TriggerMode,
)

_GATE_ID = re.compile(r'[a-z][A-Za-z0-9]*')
_TARGET_PRESET_ID = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*')
_CHECK_ID = re.compile(r'[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*')
_CHINESE = re.compile(r'[\u4e00-\u9fff]')


def _unique(values: tuple[str, ...], label: str) -> None:
    if any(not value or value != value.strip() for value in values):
        raise ValueError(f'{label} must contain non-empty trimmed strings')
    if len(values) != len(set(values)):
        raise ValueError(f'{label} must not contain duplicates')


def _description(value: str, label: str) -> None:
    if not value.endswith('。') or not _CHINESE.search(value) or '\n' in value:
        raise ValueError(f'{label} must be one Chinese sentence ending with 。')


def _repository_paths(paths: tuple[str, ...], label: str, *, allow_glob: bool) -> None:
    _unique(paths, label)
    for path in paths:
        invalid = (
            path.startswith(('/', './'))
            or '\\' in path
            or any(part == '..' for part in path.split('/'))
            or (not allow_glob and any(character in path for character in '*?[]'))
        )
        if invalid:
            raise ValueError(f'{label} contains invalid repository path: {path}')


def _unused_fields(step: RecipeStep, allowed: set[str]) -> list[str]:
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


def _validate_recipe_step(step: RecipeStep, label: str) -> None:
    if not _GATE_ID.fullmatch(step.name):
        raise ValueError(f'{label}.name has invalid identifier: {step.name}')

    allowed: set[str]
    if step.kind is RecipeStepKind.COMMAND:
        allowed = {'argv', 'required_paths', 'append_globs'}
        if not step.argv:
            raise ValueError(f'{label}.argv must not be empty')
        _repository_paths(step.required_paths, f'{label}.required_paths', allow_glob=False)
        _repository_paths(step.append_globs, f'{label}.append_globs', allow_glob=True)
    elif step.kind is RecipeStepKind.PYTHON_CHECK:
        allowed = {'check_id', 'runtime', 'args'}
        if not step.check_id or not _CHECK_ID.fullmatch(step.check_id):
            raise ValueError(f'{label}.check_id has invalid identifier')
        if step.runtime not in {'system', 'dev'}:
            raise ValueError(f'{label}.runtime has invalid value: {step.runtime}')
    elif step.kind is RecipeStepKind.GRADLE_TASK:
        allowed = {'tasks', 'args'}
        if len(step.tasks) != 1:
            raise ValueError(f'{label}.tasks must contain exactly one item')
    elif step.kind is RecipeStepKind.JAVA_RULE:
        allowed = {'rules'}
        if len(step.rules) != 1:
            raise ValueError(f'{label}.rules must contain exactly one item')
    elif step.kind is RecipeStepKind.PLAYWRIGHT:
        allowed = {'tests', 'args'}
        if not step.tests:
            raise ValueError(f'{label}.tests must not be empty')
    elif step.kind is RecipeStepKind.SCAN_SMOKE:
        allowed = {'tests', 'prerequisite_tasks', 'args'}
        if not step.tests or not step.prerequisite_tasks:
            raise ValueError(f'{label} requires tests and prerequisite_tasks')
    else:  # pragma: no cover - 新 adapter 必须先显式声明字段协议。
        raise ValueError(f'{label}.kind is unsupported: {step.kind}')

    unexpected = _unused_fields(step, allowed)
    if unexpected:
        raise ValueError(f'{label} contains fields unused by {step.kind.value}: {unexpected}')


def validate_gate_catalog(catalog: GateCatalog) -> None:
    """校验唯一 typed Catalog 的全局引用与 recipe 不变量。"""

    preset_names = tuple(preset.name for preset in catalog.target_presets)
    gate_names = tuple(gate.name for gate in catalog.gates)
    _unique(preset_names, 'TargetPreset names')
    _unique(gate_names, 'Gate names')
    if any(not _TARGET_PRESET_ID.fullmatch(name) for name in preset_names):
        raise ValueError('TargetPreset name has invalid identifier')
    if any(not _GATE_ID.fullmatch(name) for name in gate_names):
        raise ValueError('Gate name has invalid identifier')
    for preset in catalog.target_presets:
        _description(preset.description, f'TargetPreset {preset.name}.description')

    known_presets = set(preset_names)
    referenced_presets: set[str] = set()
    java_rule_owners: set[str] = set()
    for gate in catalog.gates:
        _description(gate.description, f'Gate {gate.name}.description')
        _unique(gate.target_presets, f'Gate {gate.name}.target_presets')
        unknown = sorted(set(gate.target_presets) - known_presets)
        if unknown:
            raise ValueError(f'Gate {gate.name} references unknown TargetPresets: {unknown}')
        referenced_presets.update(gate.target_presets)

        if gate.trigger.mode is TriggerMode.ALWAYS:
            if gate.trigger.paths:
                raise ValueError(f'Gate {gate.name} always trigger cannot contain paths')
        elif gate.trigger.mode is TriggerMode.CHANGED:
            if not gate.trigger.paths:
                raise ValueError(f'Gate {gate.name} changed trigger requires paths')
            _repository_paths(
                gate.trigger.paths,
                f'Gate {gate.name}.trigger.paths',
                allow_glob=True,
            )

        durations = gate.recipe.duration_expectations
        if type(durations.incremental) is not int or durations.incremental <= 0:
            raise ValueError(f'Gate {gate.name} incremental target must be a positive integer')
        if type(durations.full) is not int or durations.full <= 0:
            raise ValueError(f'Gate {gate.name} full target must be a positive integer')
        if not gate.recipe.steps:
            raise ValueError(f'Gate {gate.name} recipe must contain at least one RecipeStep')
        step_names = tuple(step.name for step in gate.recipe.steps)
        _unique(step_names, f'Gate {gate.name}.RecipeStep names')
        for index, step in enumerate(gate.recipe.steps):
            _validate_recipe_step(step, f'Gate {gate.name}.steps[{index}]')
            for rule in step.rules:
                if rule in java_rule_owners:
                    raise ValueError(f'duplicate Java rule ownership: {rule}')
                java_rule_owners.add(rule)

    empty_presets = sorted(known_presets - referenced_presets)
    if empty_presets:
        raise ValueError(f'TargetPreset selects no Gate: {empty_presets}')
