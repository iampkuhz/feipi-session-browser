#!/usr/bin/env python3
"""检查 subagent handoff、身份和验证证据契约。

完整契约可防止并行任务越界、身份混淆或静默跳过失败验证。公开入口是
`check(arguments)`；返回诊断表示主入口或 policy manifest 缺少必需约束。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
POLICY_MANIFEST = ROOT / "harness" / "agent-policy.manifest.yaml"


MAIN_DOCS = {
    "Claude main": ROOT / ".claude" / "agents" / "qwen-main-default.md",
    "Qoder main": ROOT / ".qoder" / "agents" / "qoder-main-default.md",
    "Codex model": ROOT / ".codex" / "model-instructions.md",
}

REQUIRED_HANDOFF_FIELDS = [
    "Goal",
    "Task id",
    "Task source",
    "Allowed files/directories",
    "Forbidden files/directories",
    "Required context files",
    "Expected output",
    "Validation command",
    "Failure policy",
]
REQUIRED_OUTPUT_FIELDS = [
    "Status",
    "Changed files",
    "Validation",
    "Effect checks",
    "Risks",
]
STATUS_VALUES = ["PASS", "FAIL", "BLOCKED"]
IDENTITY_TERMS = ["agent_id", "instance id"]
EVIDENCE_TERMS = ["client/session_id", "evidence"]
NON_OVERLAP_TERMS = ["不重叠", "non-overlapping"]
FAIL_VALIDATION_TERMS = ["静默跳过 validation", "silently skip validation"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _parse_size_limits(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "size_limits:":
            in_section = True
            continue
        if in_section:
            if not stripped:
                continue
            if not line.startswith(" ") and ":" in stripped:
                break
            if ":" in stripped:
                key, _, value = stripped.partition(":")
                try:
                    result[key.strip()] = int(value.strip())
                except ValueError:
                    pass
    return result


def _has_all_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term not in text]


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _has_status_values(text: str) -> bool:
    return all(re.search(rf"\b{re.escape(value)}\b", text) for value in STATUS_VALUES)


def _contains_skipped_can_pass(text: str) -> bool:
    bad_patterns = [
        r"(skipped|跳过).{0,24}(can|may|可以|可|能|算|视为).{0,24}(PASS|pass|通过)",
        r"(PASS|pass|通过).{0,24}(can|may|可以|可|能|算|视为).{0,24}(skipped|跳过)",
    ]
    protective_terms = ["不得", "不能", "不算", "non-PASS", "not PASS"]
    for pattern in bad_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            window = text[max(0, match.start() - 20) : match.end() + 20]
            if not any(term in window for term in protective_terms):
                return True
    return False


def _check_agents_md_short() -> list[str]:
    """检查 AGENTS.md 体积上限及 subagent 实例协议声明。"""
    errors: list[str] = []
    manifest_text = _read(POLICY_MANIFEST)
    if not manifest_text:
        return [f"missing {POLICY_MANIFEST.relative_to(ROOT)}"]
    agents_limit = _parse_size_limits(manifest_text).get("AGENTS.md")
    if agents_limit is None:
        return ["harness/agent-policy.manifest.yaml missing size_limits.AGENTS.md"]
    agents_path = ROOT / "AGENTS.md"
    if not agents_path.is_file():
        return ["missing AGENTS.md"]
    agents_size = agents_path.stat().st_size
    if agents_size > agents_limit:
        errors.append(f"AGENTS.md {agents_size} bytes exceeds limit {agents_limit}")
    if "subagent_instance_protocol" not in manifest_text:
        errors.append("policy manifest missing subagent_instance_protocol")
    return errors


def _check_required_handoff_fields() -> list[str]:
    """检查各主 Agent 入口是否声明完整 handoff、输出和证据聚合契约。"""
    errors: list[str] = []
    for label, path in MAIN_DOCS.items():
        text = _read(path)
        if not text:
            errors.append(f"{path.relative_to(ROOT)} missing")
            continue
        missing = _has_all_terms(text, REQUIRED_HANDOFF_FIELDS)
        if missing:
            errors.append(f"{label} missing handoff fields: {', '.join(missing)}")
        if not _has_all_terms(text, REQUIRED_OUTPUT_FIELDS) == []:
            missing_output = _has_all_terms(text, REQUIRED_OUTPUT_FIELDS)
            errors.append(f"{label} missing output fields: {', '.join(missing_output)}")
        if not _has_any(text, IDENTITY_TERMS):
            errors.append(f"{label} missing unique agent_id/instance id rule")
        if not (_has_any(text, EVIDENCE_TERMS) and "session_id" in text):
            errors.append(f"{label} missing same client/session_id evidence aggregation rule")
        if not _has_any(text, NON_OVERLAP_TERMS):
            errors.append(f"{label} missing non-overlapping parallel write scope rule")
        if not _has_any(text, FAIL_VALIDATION_TERMS):
            errors.append(f"{label} missing subagent failure cannot skip validation rule")
    return errors


def _check_status_values() -> list[str]:
    """检查共享 manifest 与主入口是否同时声明 PASS、FAIL、BLOCKED。"""
    errors: list[str] = []
    docs = {"policy manifest": POLICY_MANIFEST, **MAIN_DOCS}
    for label, path in docs.items():
        text = _read(path)
        if not _has_status_values(text):
            errors.append(f"{label} missing status values PASS/FAIL/BLOCKED")
    return errors


def _check_no_skipped_pass() -> list[str]:
    """拒绝任何把 skipped 表述为可通过的跨平台规约文本。"""
    errors: list[str] = []
    docs = {
        "AGENTS.md": ROOT / "AGENTS.md",
        "CLAUDE.md": ROOT / "CLAUDE.md",
        ".qoder/AGENTS.md": ROOT / ".qoder" / "AGENTS.md",
        **MAIN_DOCS,
    }
    for label, path in docs.items():
        text = _read(path)
        if _contains_skipped_can_pass(text):
            errors.append(f"{label} contains skipped-can-PASS wording")
    return errors


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回 subagent handoff 协议检查结果。"""
    parser = argument_parser(description='检查 subagent handoff 协议')
    parser.parse_args(arguments)
    errors: list[str] = []
    errors.extend(_check_agents_md_short())
    errors.extend(_check_required_handoff_fields())
    errors.extend(_check_status_values())
    errors.extend(_check_no_skipped_pass())
    return CheckResult.from_errors(errors)
