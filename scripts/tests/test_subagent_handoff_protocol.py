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


def _policy() -> dict:
    return yaml.safe_load(_read("harness/agent-policy.manifest.yaml"))


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
    contract = _read(
        'skills/authoring/feipi-openspec-orchestrate-change/references/subagent-contract.md'
    )
    for constraint in ('gpt-6.1-sol', 'gpt-6-luna', 'fork_turns="none"', '必要上下文'):
        assert constraint in contract


def test_shared_protocol_rejects_missing_fields_and_isolation_rules():
    """逐项破坏共享真源，证明去掉平台副本不等于只查引用。"""
    import copy
    from dataclasses import replace

    from scripts.gates.checks.agent import check_documentation as policy

    inputs = policy._load_document_inputs(ROOT)
    assert policy._check_handoff(inputs) == []
    protocol = inputs.manifest['subagent_instance_protocol']
    for key in ('required_handoff_fields', 'required_output_fields', 'status_values'):
        for field in protocol[key]:
            manifest = copy.deepcopy(inputs.manifest)
            manifest['subagent_instance_protocol'][key].remove(field)
            assert any(
                key in error for error in policy._check_handoff(replace(inputs, manifest=manifest))
            )
    shared = inputs.documents[policy.HANDOFF_CONTRACT]
    for term in [
        *protocol['required_handoff_fields'],
        *protocol['required_output_fields'],
        'PASS',
        'FAIL',
        'BLOCKED',
        'Task id',
        'agent_id',
        'client/session_id',
        '不重叠',
        '静默跳过',
    ]:
        documents = {**inputs.documents, policy.HANDOFF_CONTRACT: shared.replace(term, '')}
        assert policy._check_handoff(replace(inputs, documents=documents)), term
    for term in ('Task id', 'agent_id', 'client/session_id', '不重叠', '静默跳过'):
        manifest = copy.deepcopy(inputs.manifest)
        manifest['subagent_instance_protocol']['identity_rules'] = [
            rule.replace(term, '') for rule in protocol['identity_rules']
        ]
        assert any(
            'isolation rule' in error
            for error in policy._check_handoff(replace(inputs, manifest=manifest))
        )


def test_protocol_rejects_broken_platform_links():
    """平台断链仍阻断，薄入口无需复制字段。"""
    from dataclasses import replace

    from scripts.gates.checks.agent import check_documentation as policy

    inputs = policy._load_document_inputs(ROOT)
    for relative in (*policy.MAIN_DOCS.values(), '.claude/CLAUDE.md'):
        for reference in (policy.HANDOFF_CONTRACT, 'harness/agent-policy.manifest.yaml'):
            documents = {
                **inputs.documents,
                relative: inputs.documents[relative].replace(reference, ''),
            }
            assert any(
                'reference' in error
                for error in policy._check_handoff(replace(inputs, documents=documents))
            )


def test_shared_protocol_unreadable_is_fail(tmp_path, monkeypatch):
    """共享契约不可读时不能因为客户端只保留链接而放行。"""
    import shutil

    from scripts.gates.checks.agent import check_documentation as policy
    from scripts.gates.checks.check_protocol import CheckStatus

    for relative in (
        'harness/agent-policy.manifest.yaml',
        'AGENTS.md',
        '.codex/config.toml',
        *policy.PROTOCOL_DOCS.values(),
    ):
        if relative == policy.HANDOFF_CONTRACT:
            continue
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    monkeypatch.setattr(policy, 'ROOT', tmp_path)
    result = policy.check([])
    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'
