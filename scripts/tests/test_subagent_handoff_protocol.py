from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_subagent_protocol_checker_passes():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.gates.checks", "agent.documentation"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "GATE_RESULT status=PASS check=agent.documentation" in result.stdout


def test_required_handoff_fields_are_declared_for_all_platforms():
    required_fields = [
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
    platform_docs = [
        ".claude/agents/qwen-main-default.md",
        ".codex/model-instructions.md",
        ".qoder/agents/qoder-main-default.md",
    ]
    for doc in platform_docs:
        text = _read(doc)
        for field in required_fields:
            assert field in text, f"{doc} missing {field}"
        assert "agent_id" in text or "instance id" in text
        assert "client/session_id" in text


def test_status_values_are_declared():
    docs = [
        "harness/agent-policy.manifest.yaml",
        ".claude/agents/qwen-main-default.md",
        ".codex/model-instructions.md",
        ".qoder/agents/qoder-main-default.md",
    ]
    for doc in docs:
        text = _read(doc)
        for status in ("PASS", "FAIL", "BLOCKED"):
            assert status in text, f"{doc} missing {status}"


def test_agents_md_remains_short_index():
    manifest = _read("harness/agent-policy.manifest.yaml")
    limit_line = next(
        line for line in manifest.splitlines() if line.strip().startswith("AGENTS.md:")
    )
    limit = int(limit_line.split(":", 1)[1].strip())
    agents_path = ROOT / "AGENTS.md"
    assert agents_path.stat().st_size <= limit
    assert "subagent_instance_protocol" not in _read("AGENTS.md")


def test_qoder_delegation_structure_in_manifest():
    manifest = yaml.safe_load(_read("harness/agent-policy.manifest.yaml"))
    qd = manifest["qoder_delegation"]
    assert qd["default_implementer"] == "qoder"
    assert isinstance(qd["default_scope"], list)
    assert len(qd["default_scope"]) >= 5
    assert isinstance(qd["exceptions_codex_keeps"], list)
    assert len(qd["exceptions_codex_keeps"]) >= 3
    assert qd["max_rework_rounds"] == 2
    assert isinstance(qd["visible_dispatch_card"], list)
    assert "task_id" in qd["visible_dispatch_card"]
    assert "failure_policy" in qd["visible_dispatch_card"]
    assert isinstance(qd["parallel_constraints"], list)
    assert len(qd["parallel_constraints"]) >= 3
    assert isinstance(qd["identity_rules"], list)
    assert isinstance(qd["no_auto_features"], list)
    assert any("自动重发" in f for f in qd["no_auto_features"])


def test_agents_md_references_delegation_docs():
    text = _read("AGENTS.md")
    assert "默认实现归属" in text
    assert "qoder_delegation" in text
    assert "docs/development/qoder-subtasks.md" in text


def test_qoder_subtasks_doc_has_delegation_section():
    text = _read("docs/development/qoder-subtasks.md")
    assert "默认实现归属" in text
    assert "单一可验收目标" in text
    assert "最多 2 轮返工" in text
    assert "task id" in text.lower() or "task_id" in text
    assert "codex queue" in text
    assert "queued" in text
    assert "无需用户输入" in text


def test_qoder_runs_are_serial_even_when_codex_can_work_in_parallel():
    policy = yaml.safe_load(_read("harness/agent-policy.manifest.yaml"))["qoder_delegation"]
    assert policy["max_active_runs"] == 1
    assert policy["scheduling"] == {
        "overflow": "queue",
        "next_run_requires_confirmed_completion": True,
        "unknown_status_blocks_dispatch": True,
        "short_overlap_by_default": False,
        "codex_independent_work_allowed": True,
        "enforcement": "process-preflight-best-effort",
    }
    assert "Qoder 同时最多 1 个任务" in _read("AGENTS.md")
    doc = _read("docs/development/qoder-subtasks.md")
    assert "无锁、无自动队列" in doc
    assert "运行状态不明时不补开" in doc
    assert "Qoder 单任务调度" in _read("openspec/specs/qoder-subtask-cli/spec.md")


def test_spec_has_delegation_requirement():
    text = _read("openspec/specs/qoder-subtask-cli/spec.md")
    assert "默认实现归属" in text
    assert "SHALL" in text
    assert "SHALL NOT" in text
    assert "派发可见性" in text
    assert "返工上限" in text


def test_qoder_completion_callback_keeps_exact_parent_and_no_retry():
    policy = yaml.safe_load(_read("harness/agent-policy.manifest.yaml"))["qoder_delegation"]
    callback = policy["completion_callback"]
    assert callback == {
        "transport": "codex-queue",
        "target": "exact-parent-session-uuid",
        "completion_record_first": True,
        "automatic_retry": False,
        "queued_is_delivery_proof": False,
    }
    assert "Codex 父会话回调" in _read("openspec/specs/qoder-subtask-cli/spec.md")
