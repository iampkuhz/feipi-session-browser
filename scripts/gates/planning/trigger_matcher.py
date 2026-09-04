"""把 changed files 匹配到 Gate Trigger pattern，并保留可解释证据。

本模块只实现跨平台 pattern 语义和 file → pattern → Gate 因果链；不负责读取 Git、
不选择 selector，不执行 Gate。由 plan compiler 在冻结 GatePlan 时调用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.gates.catalog.gate_contracts import Gate, TriggerMode

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class TriggerMatch:
    """记录一条 file → pattern → Gate 因果边。"""

    file: str
    pattern: str
    gate_name: str


@dataclass(frozen=True, slots=True)
class NotTriggeredGate:
    """说明某个 Gate 未被选入计划的原因。"""

    gate_name: str
    reason: str


def normalize_repo_path(path: str) -> str:
    """规范化 repository-relative path，用于跨平台匹配。"""

    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def trigger_pattern_matches(path: str, pattern: str) -> bool:
    """使用仓库统一的 ``**``/``*``/``?`` 确定性 glob 语义。"""

    normalized_path = normalize_repo_path(path)
    normalized_pattern = normalize_repo_path(pattern)
    regex = re.escape(normalized_pattern)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.fullmatch(regex, normalized_path))


def match_trigger(changed_files: Iterable[str], gates: Iterable[Gate]) -> tuple[TriggerMatch, ...]:
    """按 Gate、file、pattern 顺序返回所有稳定 Trigger 原因。"""

    files = tuple(normalize_repo_path(path) for path in changed_files)
    matches: list[TriggerMatch] = []
    for gate in gates:
        if gate.trigger.mode is TriggerMode.ALWAYS:
            matches.append(TriggerMatch('<always>', '<always>', gate.name))
            continue
        for path in files:
            for pattern in gate.trigger.paths:
                if trigger_pattern_matches(path, pattern):
                    matches.append(TriggerMatch(path, pattern, gate.name))
    return tuple(matches)
