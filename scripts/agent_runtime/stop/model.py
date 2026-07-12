"""定义 Stop 七阶段共享的 typed model 与终态不变量。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class StopPhase(StrEnum):
    """Stop 唯一管道的七个有序阶段。"""

    IDENTITY = 'identity'
    LOCK = 'lock'
    EVIDENCE = 'evidence'
    REENTRY_RECOVERY = 'reentry-recovery'
    GATE = 'gate'
    REPORT = 'report'
    FINALIZE = 'finalize'


class StopTerminalState(StrEnum):
    """Stop 对调用端公开的稳定终态，NOT_TRIGGERED 不等同 PASS。"""

    PASS = 'PASS'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'


@dataclass(slots=True)
class StopContext:
    """贯穿 Stop 七阶段的唯一可变上下文，集中保存证据和关闭状态。"""

    agent: str
    raw_context: dict[str, Any]
    handoff_on_failure: bool = False
    adapter_mode: str = 'hook'
    phase: StopPhase = StopPhase.IDENTITY
    terminal_state: StopTerminalState = StopTerminalState.BLOCKED
    repo_root: Path | None = None
    hook_context: Any = None
    identity: Any = None
    record: dict[str, Any] = field(default_factory=dict)
    checkout_facts: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    git_evidence: dict[str, Any] = field(default_factory=lambda: {'changedFiles': []})
    changed_files: list[str] = field(default_factory=list)
    baseline_dirty_files: set[str] = field(default_factory=set)
    evidence_mode: str = 'git-run-record'
    change_id: str = 'unknown'
    targets: list[str] = field(default_factory=list)
    read_only: bool = True
    resource_lock_names: list[str] = field(default_factory=list)
    gates_ok: bool = True
    runtime_ok: bool = True
    lock_status: str = 'blocked'
    continuation_count: int = 0
    outcome_record: dict[str, Any] = field(default_factory=dict)
    gate_result: Any = None
    gate_results: list[dict[str, str]] = field(default_factory=list)
    circuit_broken: bool = False
    circuit_state: str = 'CLOSED'
    runtime_root: Path | None = None
    run_dir: Path | None = None
    audit_dir: Path | None = None
    reentry_path: Path | None = None
    summary_path: Path | None = None
    report_path: Path | None = None
    recovery_scope: dict[str, str] = field(default_factory=dict)
    stop_lock: Any = None
