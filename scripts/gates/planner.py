"""把 changed files 确定性转换为不可变 Gate plan，不执行任何命令。

不负责产品业务处理；由 Gate CLI 或 Stop pipeline 调用。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.gates.catalog import (
    CATALOG,
    GATES,
    TARGETS,
    gate_by_name,
    target_by_name,
    tier_by_name,
)
from scripts.gates.model import FileClassification, GatePlan, TargetGatePlan

if TYPE_CHECKING:
    from collections.abc import Iterable


# 规范化 repository-relative path，兼容 Windows 分隔符与 ``./`` 前缀。
def normalize_repo_path(path: str) -> str:
    """规范化 repository-relative path，兼容 Windows 分隔符与 ``./`` 前缀。"""
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 按历史 Gate glob 语义匹配路径，保证迁移前后触发结果一致。
def pattern_matches(path: str, pattern: str) -> bool:
    """按历史 Gate glob 语义匹配路径，保证迁移前后触发结果一致。"""
    normalized_path = normalize_repo_path(path)
    normalized_pattern = normalize_repo_path(pattern)
    regex = re.escape(normalized_pattern)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', normalized_path))


# 按 catalog 的首个命中规则分类单个 path，未知路径保持历史默认允许语义。
def classify_path(path: str) -> FileClassification:
    """按 catalog 的首个命中规则分类单个 path，未知路径保持历史默认允许语义。"""
    normalized = normalize_repo_path(path)
    for rule in CATALOG.path_rules:
        if any(pattern_matches(normalized, pattern) for pattern in rule.patterns):
            return FileClassification(
                file=normalized,
                category=rule.category,
                requires_quality_gate=rule.requires_quality_gate,
                quality_target=rule.quality_target,
                risk_level=rule.risk_level,
                allowed_by_default=rule.allowed_by_default,
            )
    return FileClassification(
        file=normalized,
        category='unknown',
        requires_quality_gate=False,
        quality_target=None,
        risk_level='low',
        allowed_by_default=True,
    )


# 保持输入顺序分类一组 path，并返回不可变结果。
def classify_files(paths: Iterable[str]) -> tuple[FileClassification, ...]:
    """保持输入顺序分类一组 path，并返回不可变结果。"""
    return tuple(classify_path(path) for path in paths)


# 由分类规则与 scan smoke 附加规则派生历史 raw target 顺序。
def required_quality_targets(files: Iterable[str]) -> list[str]:
    """由分类规则与 scan smoke 附加规则派生历史 raw target 顺序。"""
    normalized_files = [normalize_repo_path(path) for path in files]
    targets: list[str] = []
    for classification in classify_files(normalized_files):
        target = classification.quality_target
        if classification.requires_quality_gate and target and target not in targets:
            targets.append(target)
    for path in normalized_files:
        if any(pattern_matches(path, pattern) for pattern in CATALOG.scan_script_smoke_patterns):
            if 'scan-script-smoke' not in targets:
                targets.append('scan-script-smoke')
    return targets


# 应用 catalog dominance，保持历史顺序并移除已被 dominant target 覆盖的 target。
def effective_targets(targets: Iterable[str]) -> list[str]:
    """应用 catalog dominance，保持历史顺序并移除已被 dominant target 覆盖的 target。"""
    source = list(targets)
    result = list(source)
    for name in source:
        target = target_by_name(name)
        for included in target.includes:
            if included in result:
                result.remove(included)
    return result


# 按 catalog 的 target 内 order 返回全量 baseline Gate 名称。
def required_gates_for_target(target: str) -> list[str]:
    """按 catalog 的 target 内 order 返回全量 baseline Gate 名称。"""
    target_by_name(target)
    rules = sorted(
        (
            (rule.order, gate.name)
            for gate in GATES
            for rule in gate.target_rules
            if rule.target == target
        ),
        key=lambda item: item[0],
    )
    return [name for _, name in rules]


# 按增量 pattern 选择 applicable Gate；``None`` 表示完整 baseline。
def applicable_gates_for_target(
    target: str, changed_files: Iterable[str] | None = None
) -> list[str]:
    """按增量 pattern 选择 applicable Gate；``None`` 表示完整 baseline。"""
    baseline = required_gates_for_target(target)
    if changed_files is None:
        return baseline
    normalized_files = tuple(normalize_repo_path(path) for path in changed_files)
    applicable: list[str] = []
    for gate_name in baseline:
        gate = gate_by_name(gate_name)
        rule = next(rule for rule in gate.target_rules if rule.target == target)
        if not rule.patterns or any(
            pattern_matches(path, pattern) for path in normalized_files for pattern in rule.patterns
        ):
            applicable.append(gate_name)
    return applicable


# 为现有 executor 提供由 typed target spec 派生的并发元数据快照。
def target_parallel_meta(target: str) -> dict[str, object]:
    """为现有 executor 提供由 typed target spec 派生的并发元数据快照。"""
    spec = next((item for item in TARGETS if item.name == target), None)
    if spec is None:
        return {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300}
    return {
        'parallel_safe': spec.parallel_safe,
        'exclusive_resources': list(spec.exclusive_resources),
        'timeout': spec.timeout_seconds,
    }


# 验证 target 已注册；未知 target 抛出 ``ValueError``。
def validate_target(target: str) -> None:
    """验证 target 已注册；未知 target 抛出 ``ValueError``。"""
    target_by_name(target)


# 从 Gate 自身 tiers 字段返回该档位的逻辑 Gate 集合。
def gates_for_tier(tier: str) -> frozenset[str]:
    """从 Gate 自身 tiers 字段返回该档位的逻辑 Gate 集合。"""
    tier_by_name(tier)
    names = tuple(gate.name for gate in GATES if tier in gate.tiers)
    return frozenset(names)


# 为现有 CLI 派生 tier 描述与失败策略，不复制 tier 真相。
def tier_metadata() -> dict[str, dict[str, str]]:
    """返回：
    当前函数的稳定结果。
    """
    return {
        tier.name: {
            'description': tier.description,
            'failure_policy': tier.failure_policy,
        }
        for tier in CATALOG.tiers
    }


# 冻结 classification、raw/effective target 与 applicable Gate 的完整计划。
def plan(
    changed_files: Iterable[str],
    targets: Iterable[str] | None = None,
    *,
    tier: str = 'required',
    incremental: bool = True,
) -> GatePlan:
    """冻结 classification、raw/effective target 与 applicable Gate 的完整计划。"""
    files = tuple(normalize_repo_path(path) for path in changed_files)
    classifications = classify_files(files)
    raw = tuple(required_quality_targets(files) if targets is None else targets)
    effective = tuple(effective_targets(raw))
    allowed_gates = gates_for_tier(tier)
    target_plans = tuple(
        TargetGatePlan(
            target=target,
            gates=tuple(
                gate_by_name(name)
                for name in (
                    applicable_gates_for_target(target, files)
                    if incremental
                    else required_gates_for_target(target)
                )
                if name in allowed_gates
            ),
        )
        for target in effective
    )
    return GatePlan(
        changed_files=files,
        classifications=classifications,
        raw_targets=raw,
        effective_targets=effective,
        targets=target_plans,
    )


# 验证 catalog 唯一、引用完整且 target dominance/Gate includedBy 无环。
def validate_catalog() -> None:
    """返回：
    当前函数的稳定结果。
    """
    gate_names = [gate.name for gate in GATES]
    target_names = [target.name for target in TARGETS]
    if len(gate_names) != len(set(gate_names)):
        raise ValueError('duplicate Gate name in catalog')
    if len(target_names) != len(set(target_names)):
        raise ValueError('duplicate target name in catalog')
    known_gates = set(gate_names)
    known_targets = set(target_names)
    for gate in GATES:
        if not gate.description.strip() or not gate.description.endswith('。'):
            raise ValueError(f'Gate description must be Chinese prose: {gate.name}')
        if bool(gate.command_key) == bool(gate.gradle_tasks):
            raise ValueError(f'Gate needs exactly one command source: {gate.name}')
        if not gate.target_rules or any(
            rule.target not in known_targets for rule in gate.target_rules
        ):
            raise ValueError(f'Gate target reference is invalid: {gate.name}')
        if not gate.changed_files_input:
            raise ValueError(f'Gate changed-files input is invalid: {gate.name}')
        if any(parent not in known_gates for parent in gate.included_by):
            raise ValueError(f'Gate includedBy reference is invalid: {gate.name}')
    _assert_acyclic(
        {target.name: target.includes for target in TARGETS},
        'target dominance',
    )
    _assert_acyclic(
        {gate.name: gate.included_by for gate in GATES},
        'Gate includedBy',
    )


# 对 catalog 小型有向图执行确定性 DFS 环检测。
def _assert_acyclic(graph: dict[str, tuple[str, ...]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    # 访问单个图节点并检测回边。
    def visit(node: str) -> None:
        """参数：
        node: 当前待访问的 catalog 节点。
        """
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
