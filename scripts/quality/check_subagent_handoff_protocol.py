#!/usr/bin/env python3
"""Check subagent handoff, identity, evidence, and validation reporting rules."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GATE_NAME = "subagentHandoffProtocol"
POLICY_MANIFEST = ROOT / "harness" / "agent-policy.manifest.yaml"

from scripts.quality._trigger import add_changed_files_arg, parse_changed_files, skip_if_not_triggered

TRIGGER_PATTERNS = [
    'AGENTS.md', 'CLAUDE.md',
    '.agents/**', '.claude/**', '.codex/**', '.qoder/**',
    'skills/**', 'harness/**',
    'scripts/claude_hooks/**/*.py', 'scripts/hooks/**/*.py',
    'scripts/agent_hooks/**/*.py', 'scripts/harness/**/*.py',
    'scripts/harness/**/*.sh', 'scripts/quality/**/*.py',
]

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


# 维护 _failures_to_exit 函数行为。
def _failures_to_exit(errors: list[str]) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if errors:
        for error in errors:
            print(f"[{GATE_NAME}] FAIL: {error}")
        return 1
    print(f"[{GATE_NAME}] PASS: subagent handoff protocol is declared and checkable")
    return 0


# 维护 _read 函数行为。
def _read(path: Path) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return path.read_text(encoding="utf-8") if path.is_file() else ""


# 维护 _parse_size_limits 函数行为。
def _parse_size_limits(text: str) -> dict[str, int]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
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


# 维护 _has_all_terms 函数行为。
def _has_all_terms(text: str, terms: list[str]) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return [term for term in terms if term not in text]


# 维护 _has_any 函数行为。
def _has_any(text: str, terms: list[str]) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return any(term in text for term in terms)


# 维护 _has_status_values 函数行为。
def _has_status_values(text: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return all(re.search(rf"\b{re.escape(value)}\b", text) for value in STATUS_VALUES)


# 维护 _contains_skipped_can_pass 函数行为。
def _contains_skipped_can_pass(text: str) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
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


# 维护 check_agents_md_short 函数行为。
def check_agents_md_short() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
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
    print(f"[{GATE_NAME}] PASS: AGENTS.md {agents_size} bytes <= {agents_limit}")
    return errors


# 维护 check_required_handoff_fields 函数行为。
def check_required_handoff_fields() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
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
    if not errors:
        print(f"[{GATE_NAME}] PASS: handoff fields and identity rules declared")
    return errors


# 维护 check_status_values 函数行为。
def check_status_values() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    errors: list[str] = []
    docs = {"policy manifest": POLICY_MANIFEST, **MAIN_DOCS}
    for label, path in docs.items():
        text = _read(path)
        if not _has_status_values(text):
            errors.append(f"{label} missing status values PASS/FAIL/BLOCKED")
    if not errors:
        print(f"[{GATE_NAME}] PASS: status values PASS/FAIL/BLOCKED declared")
    return errors


# 维护 check_no_skipped_pass 函数行为。
def check_no_skipped_pass() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
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
    if not errors:
        print(f"[{GATE_NAME}] PASS: skipped checks are not documented as PASS")
    return errors


# 维护 main 函数行为。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
        skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)
    else:
        skip_if_not_triggered(None, TRIGGER_PATTERNS)

    errors: list[str] = []
    errors.extend(check_agents_md_short())
    errors.extend(check_required_handoff_fields())
    errors.extend(check_status_values())
    errors.extend(check_no_skipped_pass())
    return _failures_to_exit(errors)


if __name__ == "__main__":
    raise SystemExit(main())
