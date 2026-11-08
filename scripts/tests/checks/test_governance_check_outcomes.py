"""验证 Agent 与源码治理 Check 区分仓库违规和执行失败。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.gates.checks.agent import check_documentation as document_policy
from scripts.gates.checks.agent import check_entrypoints as runtime_policy
from scripts.gates.checks.agent import check_skill_registry as skill_registry
from scripts.gates.checks.check_protocol import CheckStatus

if TYPE_CHECKING:
    from pathlib import Path


def _assert_execution_failure(result, reason: str) -> None:
    """断言 Check 没有形成仓库结论，并保留稳定失败原因。"""
    assert result.status is CheckStatus.FAIL
    assert result.reason == reason
    assert result.diagnostics


def test_protected_roots_yaml_violation_is_blocked(tmp_path: Path, monkeypatch) -> None:
    """YAML 内容错误是仓库配置违规，不应伪装成执行失败。"""
    (tmp_path / 'harness').mkdir()
    (tmp_path / 'harness' / 'agent-policy.manifest.yaml').write_text('[invalid', encoding='utf-8')
    (tmp_path / 'AGENTS.md').write_text('', encoding='utf-8')
    monkeypatch.setattr(document_policy, 'ROOT', tmp_path)

    monkeypatch.setattr(
        document_policy,
        '_load_document_inputs',
        lambda: (_ for _ in ()).throw(__import__('yaml').YAMLError('invalid')),
    )
    assert document_policy.check([]).status is CheckStatus.BLOCKED


def test_document_policy_required_files_missing_is_fail(tmp_path: Path, monkeypatch) -> None:
    """合并检查的任一必需输入不可用时无法形成完整政策结论。"""
    monkeypatch.setattr(document_policy, 'ROOT', tmp_path)

    _assert_execution_failure(document_policy.check([]), 'input-unavailable')


def test_skill_registry_read_error_is_fail(monkeypatch) -> None:
    """registry 读取异常必须返回 FAIL 和输入不可用原因。"""
    monkeypatch.setattr(
        skill_registry, '_load_registry', lambda: (_ for _ in ()).throw(OSError('denied'))
    )

    _assert_execution_failure(skill_registry.check([]), 'input-unavailable')


def test_skill_registry_yaml_violation_is_blocked(monkeypatch) -> None:
    """registry YAML 内容错误仍属于需要修改仓库的 BLOCKED。"""
    monkeypatch.setattr(skill_registry, '_load_registry', lambda: None)

    assert skill_registry.check([]).status is CheckStatus.BLOCKED


def test_skill_registry_missing_is_blocked(tmp_path: Path, monkeypatch) -> None:
    """仓库必须维护的 registry 明确缺失时已经形成 BLOCKED 结论。"""
    monkeypatch.setattr(skill_registry, 'ROOT', tmp_path)
    monkeypatch.setattr(skill_registry, 'REGISTRY', tmp_path / 'harness' / 'skill-registry.yaml')

    assert skill_registry.check([]).status is CheckStatus.BLOCKED


def test_permission_json_content_violation_is_blocked(monkeypatch) -> None:
    """JSON 语法错误是政策配置违规，而不是 runtime 异常。"""
    import json

    monkeypatch.setattr(
        runtime_policy,
        '_load_runtime_inputs',
        lambda: (_ for _ in ()).throw(json.JSONDecodeError('invalid', '', 0)),
    )
    assert runtime_policy.check([]).status is CheckStatus.BLOCKED


def test_codex_policy_read_error_is_fail(monkeypatch) -> None:
    """Agent 文件读取失败时不能产出虚假的政策结论。"""
    monkeypatch.setattr(
        runtime_policy,
        '_load_runtime_inputs',
        lambda: (_ for _ in ()).throw(OSError('denied')),
    )

    _assert_execution_failure(runtime_policy.check([]), 'input-unavailable')


def test_entry_parity_yaml_content_violation_is_blocked(monkeypatch) -> None:
    """manifest 语法错误应要求修改配置，因此返回 BLOCKED。"""
    import yaml

    monkeypatch.setattr(
        runtime_policy,
        '_load_runtime_inputs',
        lambda: (_ for _ in ()).throw(yaml.YAMLError('invalid')),
    )

    assert runtime_policy.check([]).status is CheckStatus.BLOCKED
