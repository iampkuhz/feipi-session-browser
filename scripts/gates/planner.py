"""把 changed files 确定性转换为不可变 Gate plan，不执行任何命令。

不负责产品业务处理；由 Gate CLI 或 Stop pipeline 调用。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.gates.catalog import (
    CATALOG,
    GATES,
    gate_by_name,
    target_by_name,
    tier_by_name,
    validate_catalog_schema,
)
from scripts.gates.model import FileClassification, GatePlan, TargetGatePlan

if TYPE_CHECKING:
    from collections.abc import Iterable


def normalize_repo_path(path: str) -> str:
    """规范化 repository-relative path，兼容 Windows 分隔符与 ``./`` 前缀。"""
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


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


def classify_path(path: str) -> FileClassification:
    """按 catalog 的首个命中规则分类单个 path，未知路径保持历史默认允许语义。"""
    normalized = normalize_repo_path(path)
    for rule in CATALOG.path_rules:
        if any(pattern_matches(normalized, pattern) for pattern in rule.patterns):
            return FileClassification(
                file=normalized,
                category=rule.category,
                targets=rule.targets,
                risk_level=rule.risk_level,
                allowed=rule.allowed,
            )
    return FileClassification(
        file=normalized,
        category='unknown',
        targets=(),
        risk_level='low',
        allowed=True,
    )


def classify_files(paths: Iterable[str]) -> tuple[FileClassification, ...]:
    """保持输入顺序分类一组 path，并返回不可变结果。"""
    return tuple(classify_path(path) for path in paths)


def required_quality_targets(files: Iterable[str]) -> list[str]:
    """由分类规则与 scan smoke 附加规则派生历史 raw target 顺序。"""
    normalized_files = [normalize_repo_path(path) for path in files]
    targets: list[str] = []
    for classification in classify_files(normalized_files):
        for target in classification.targets:
            if target not in targets:
                targets.append(target)
    for trigger in CATALOG.target_triggers:
        if (
            any(
                pattern_matches(path, pattern)
                for path in normalized_files
                for pattern in trigger.patterns
            )
            and trigger.target not in targets
        ):
            targets.append(trigger.target)
    return targets


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


def validate_target(target: str) -> None:
    """验证 target 已注册；未知 target 抛出 ``ValueError``。"""
    target_by_name(target)


def gates_for_tier(tier: str) -> frozenset[str]:
    """按 minimum tier 返回该档位的逻辑 Gate 集合。"""
    tier_by_name(tier)
    rank = {'quick': 0, 'required': 1, 'full': 2}
    names = tuple(gate.name for gate in GATES if rank[gate.minimum_tier.value] <= rank[tier])
    return frozenset(names)


def tier_metadata() -> dict[str, dict[str, str]]:
    """从 catalog 派生 tier 描述与失败策略。"""
    return {
        'quick': {
            'description': '本地开发默认快速反馈，只运行轻量级 Gate 子集。',
            'failure_policy': 'triggered Gate 必须 PASS；not triggered 不算 skipped。',
        },
        'required': {
            'description': 'PR 合入和 Stop/handoff 前必须通过。',
            'failure_policy': '0 skipped outcome；skipped 即 FAIL/BLOCKED。',
        },
        'full': {
            'description': '发布或大迁移收口前运行，包含全部 target 和额外验证。',
            'failure_policy': '0 skipped outcome；skipped 即 FAIL/BLOCKED。',
        },
    }


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


def validate_catalog() -> None:
    """校验当前唯一 catalog 声明。"""
    validate_catalog_schema(CATALOG)
