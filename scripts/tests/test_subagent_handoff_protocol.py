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


def _policy() -> dict:
    return yaml.safe_load(_read("harness/agent-policy.manifest.yaml"))


def test_native_handoff_and_result_contract():
    protocol = _policy()["subagent_instance_protocol"]
    assert protocol["required_handoff_fields"] == [
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
    assert protocol["required_output_fields"] == [
        "Status",
        "Changed files",
        "Validation",
        "Effect checks",
        "Risks",
    ]
    assert protocol["status_values"] == ["PASS", "FAIL", "BLOCKED"]
    rules = "\n".join(protocol["identity_rules"])
    for constraint in ("Task id", "agent_id", "不重叠写范围", "client/session_id", "不得静默跳过"):
        assert constraint in rules
    contract = _read(
        "skills/authoring/feipi-openspec-orchestrate-change/references/subagent-contract.md"
    )
    for field in protocol["required_handoff_fields"] + protocol["required_output_fields"]:
        assert field in contract
    assert "client/session_id" in contract
    assert "不回滚" in _read(".codex/model-instructions.md") or "不得扩大范围或回滚" in contract


def test_native_model_routing_and_host_constraints():
    policy = _policy()["native_delegation"]
    assert policy["implementation"] == "current-agent-native-subagents"
    assert policy["handoff_protocol"] == "subagent_instance_protocol"
    assert policy["model_routing"] == {
        "important_implementation": "gpt-6.1-sol",
        "complex_analysis": "gpt-6.1-sol",
        "independent_validation": "gpt-6.1-sol",
        "lightweight_lookup": "gpt-6-luna",
    }
    host = "\n".join(policy["host_constraints"])
    assert "fork_turns=none" in host
    assert "必要上下文" in host
    assert "不固定所有角色模型" in host
    assert "main 接管或调整范围" in host
    for doc in (".codex/model-instructions.md", "docs/agent-runtime.md"):
        text = _read(doc)
        for constraint in ("gpt-6.1-sol", "gpt-6-luna", 'fork_turns="none"', "必要上下文"):
            assert constraint in text, f"{doc} missing {constraint}"


def test_native_lifecycle_and_permissions_do_not_create_another_scheduler():
    policy = _policy()["native_delegation"]
    lifecycle = "\n".join(policy["lifecycle"])
    for constraint in ("spawn_agent/followup_task", "原生等待/完成事件", "串行集成", "写范围互斥"):
        assert constraint in lifecycle
    for forbidden in (
        "CLI",
        "调度器",
        "队列",
        "receipt",
        "callback",
        "watchdog",
        "ack",
        "仓库状态机",
    ):
        assert forbidden in lifecycle
    permissions = "\n".join(policy["permissions"])
    assert "保持当前环境权限" in permissions
    assert "不继承 Qoder bypass_permissions 默认值" in permissions
    assert "不因失败升级权限" in permissions
    assert "不降低 Gate" in permissions
    assert "qoder_delegation" not in _policy()
    assert "default_permission_mode" not in policy


def test_native_evidence_is_current_and_requires_independent_validation():
    policy = _policy()["native_delegation"]
    retired = "\n".join(policy["retired_evidence"])
    assert "旧 Qoder PASS 不得作为原生子任务或本次验收证据" in retired
    assert "只识别为已退役" in retired
    assert "不恢复或重新执行旧调度链" in retired
    validation = "\n".join(policy["validation"])
    assert "不替代 main 独立运行 required checks" in validation
    for nonpass in ("failed", "warning", "skipped", "not-run", "unavailable"):
        assert nonpass in validation
    assert "产品 Qoder session" in policy["product_boundary"]
    assert "安全保护" in policy["product_boundary"]
    assert "ignored 个人数据" in policy["product_boundary"]


def test_native_docs_and_spec_are_active_contract():
    agents = _read("AGENTS.md")
    assert "原生子任务" in agents
    assert "docs/agent-runtime.md" in agents
    assert "qoder_delegation" not in agents
    assert not (ROOT / "docs/development/qoder-subtasks.md").exists()
    assert not (ROOT / "openspec/specs/qoder-subtask-cli/spec.md").exists()
    spec = _read("openspec/specs/native-subagent-delegation/spec.md")
    for requirement in (
        "当前 Agent 原生委派",
        "复用共享 handoff 与证据隔离",
        "权限和验证真实性保持",
        "gpt-6.1-sol",
        "gpt-6-luna",
        "client/session_id",
        "SHALL NOT",
        "产品 Qoder session",
    ):
        assert requirement in spec
