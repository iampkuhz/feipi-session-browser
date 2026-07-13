#!/usr/bin/env python3
"""本模块负责检查 subagent handoff、身份与验证证据契约。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.checks._framework import repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
GATE_NAME = "subagentHandoffProtocol"
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


def _failures_to_exit(errors: list[str]) -> int:
    if errors:
        for error in errors:
            print(f"[{GATE_NAME}] FAIL: {error}")
        return 1
    return 0


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


def check_agents_md_short() -> list[str]:
    """检查 `check_agents_md_short` 对应的仓库契约；发现不一致时返回结构化失败信息。"""
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


def check_required_handoff_fields() -> list[str]:
    """检查 `check_required_handoff_fields` 对应的仓库契约；发现不一致时返回结构化失败信息。"""
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


def check_status_values() -> list[str]:
    """检查 `check_status_values` 对应的仓库契约；发现不一致时返回结构化失败信息。"""
    errors: list[str] = []
    docs = {"policy manifest": POLICY_MANIFEST, **MAIN_DOCS}
    for label, path in docs.items():
        text = _read(path)
        if not _has_status_values(text):
            errors.append(f"{label} missing status values PASS/FAIL/BLOCKED")
    if not errors:
        print(f"[{GATE_NAME}] PASS: status values PASS/FAIL/BLOCKED declared")
    return errors


def check_no_skipped_pass() -> list[str]:
    """检查 `check_no_skipped_pass` 对应的仓库契约；发现不一致时返回结构化失败信息。"""
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


def main() -> int:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""

    errors: list[str] = []
    errors.extend(check_agents_md_short())
    errors.extend(check_required_handoff_fields())
    errors.extend(check_status_values())
    errors.extend(check_no_skipped_pass())
    return _failures_to_exit(errors)
