"""按 Gate Trigger 或人工 selector 生成稳定计划。

本模块负责为 CLI 和 Executor 冻结有序 Gate 列表，不负责加载配置或执行命令；自动增量选择
只读取每个 Gate 自己的 Trigger，人工 Target 仅作为显式预设使用。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.gates.catalog import (
    CATALOG,
    GATES,
    gate_by_name,
    target_by_name,
    validate_catalog_schema,
)
from scripts.gates.model import ExecutionMode, FileClassification, GatePlan, GateSpec, TriggerMode

if TYPE_CHECKING:
    from collections.abc import Iterable


def normalize_repo_path(path: str) -> str:
    """规范化 repository-relative path，兼容 Windows 分隔符与 ``./`` 前缀。"""

    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def pattern_matches(path: str, pattern: str) -> bool:
    """使用唯一的跨平台 glob 语义匹配一个 repository-relative path。"""

    normalized_path = normalize_repo_path(path)
    normalized_pattern = normalize_repo_path(pattern)
    regex = re.escape(normalized_pattern)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.fullmatch(regex, normalized_path))


def classify_path(path: str) -> FileClassification:
    """按首个命中规则分类路径，但不再由分类派生 Target。"""

    normalized = normalize_repo_path(path)
    for rule in CATALOG.path_rules:
        if any(pattern_matches(normalized, pattern) for pattern in rule.patterns):
            return FileClassification(normalized, rule.category, rule.risk_level, rule.allowed)
    return FileClassification(normalized, 'unknown', 'low', True)


def classify_files(paths: Iterable[str]) -> tuple[FileClassification, ...]:
    """保持输入顺序返回路径治理分类。"""

    return tuple(classify_path(path) for path in paths)


def gate_matches(gate: GateSpec, changed_files: Iterable[str]) -> bool:
    """判断 Gate 是否被自动 incremental 规划选中。"""

    if gate.trigger.mode is TriggerMode.ALWAYS:
        return True
    return any(
        pattern_matches(path, pattern) for path in changed_files for pattern in gate.trigger.paths
    )


def gates_for_target(target: str) -> tuple[GateSpec, ...]:
    """按 Catalog 声明顺序返回一个人工 Target preset 的成员。"""

    target_by_name(target)
    members = tuple(gate for gate in GATES if target in gate.targets)
    if not members:
        raise ValueError(f'quality Target selects no Gate: {target}')
    return members


def plan(
    changed_files: Iterable[str] = (),
    *,
    mode: ExecutionMode | str = ExecutionMode.INCREMENTAL,
    target: str | None = None,
    gate: str | None = None,
) -> GatePlan:
    """按 mode×selector 矩阵冻结计划；Target 永不参与自动选择。"""

    if target is not None and gate is not None:
        raise ValueError('target and gate selectors are mutually exclusive')
    selected_mode = ExecutionMode(mode)
    files = tuple(normalize_repo_path(path) for path in changed_files)
    if selected_mode is ExecutionMode.FULL and files:
        raise ValueError('full mode does not accept changed files')

    selector: str | None = None
    selector_value: str | None = None
    if gate is not None:
        selected = (gate_by_name(gate),)
        selector, selector_value = 'gate', gate
    elif target is not None:
        selected = gates_for_target(target)
        selector, selector_value = 'target', target
    elif selected_mode is ExecutionMode.FULL:
        selected = GATES
    else:
        selected = tuple(spec for spec in GATES if gate_matches(spec, files))

    return GatePlan(selected_mode, files, selected, selector, selector_value)


def validate_catalog() -> None:
    """校验当前唯一 Catalog 声明。"""

    validate_catalog_schema(CATALOG)
