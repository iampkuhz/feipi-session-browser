"""验证 Agent 与源码治理 Check 区分仓库违规和执行失败。"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.gates.checks.agent import check_documentation as document_policy
from scripts.gates.checks.agent import check_entrypoints as runtime_policy
from scripts.gates.checks.agent import check_skill_registry as skill_registry
from scripts.gates.checks.check_protocol import CheckStatus
from scripts.gates.checks.repository import check_maintenance_language as language_policy
from scripts.gates.checks.source import check_code_comment_language as comment_language

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
        lambda _root: (_ for _ in ()).throw(__import__('yaml').YAMLError('invalid')),
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
        lambda _root: (_ for _ in ()).throw(json.JSONDecodeError('invalid', '', 0)),
    )
    assert runtime_policy.check([]).status is CheckStatus.BLOCKED


def test_codex_policy_read_error_is_fail(monkeypatch) -> None:
    """Agent 文件读取失败时不能产出虚假的政策结论。"""
    monkeypatch.setattr(
        runtime_policy,
        '_load_runtime_inputs',
        lambda _root: (_ for _ in ()).throw(OSError('denied')),
    )

    _assert_execution_failure(runtime_policy.check([]), 'input-unavailable')


def test_entry_parity_yaml_content_violation_is_blocked(monkeypatch) -> None:
    """manifest 语法错误应要求修改配置，因此返回 BLOCKED。"""
    import yaml

    monkeypatch.setattr(
        runtime_policy,
        '_load_runtime_inputs',
        lambda _root: (_ for _ in ()).throw(yaml.YAMLError('invalid')),
    )

    assert runtime_policy.check([]).status is CheckStatus.BLOCKED


def test_comment_policy_missing_is_fail_but_invalid_json_is_blocked(
    tmp_path: Path,
) -> None:
    """术语政策不可读与政策内容错误必须形成不同结论。"""
    missing = comment_language.check(['--policy', str(tmp_path / 'missing.json')])
    invalid_path = tmp_path / 'invalid.json'
    invalid_path.write_text('{invalid', encoding='utf-8')
    invalid = comment_language.check(['--policy', str(invalid_path)])

    _assert_execution_failure(missing, 'input-unavailable')
    assert invalid.status is CheckStatus.BLOCKED


def test_language_policy_invalid_changed_files_does_not_silently_pass() -> None:
    """显式 changed-files 无效时禁止回退成空扫描后 PASS。"""
    result = language_policy.check(['--changed-files', '{invalid'])

    _assert_execution_failure(result, 'input-unavailable')


@pytest.mark.parametrize(
    'line',
    [
        'Use this skill only for this repository.',
        'developer_instructions = "Run deterministic validation and report evidence."',
    ],
)
def test_language_policy_blocks_english_narrative(line: str) -> None:
    """原隐藏自测的英文叙述正例由真实 pytest 保护。"""
    assert language_policy._line_violates(line)


@pytest.mark.parametrize(
    'line',
    [
        '默认使用简体中文, 命令名如 `pytest` 保持英文。',
        'model = "gpt-5.4-mini"',
        '- Validation: `python3 scripts/gates/cli.py run --mode full --target agent-governance` passed.',
    ],
)
def test_language_policy_allows_chinese_or_technical_lines(line: str) -> None:
    """原隐藏自测的中文、标识符和命令行反例由真实 pytest 保护。"""
    assert not language_policy._line_violates(line)


@pytest.mark.parametrize('error', [OSError('git missing'), subprocess.CalledProcessError(2, 'git')])
def test_language_policy_git_failure_does_not_silently_pass(monkeypatch, error: Exception) -> None:
    """Git 不能提供增量文件时必须 FAIL，不能把未扫描解释为通过。"""
    # Gate executor 会为 pytest 注入增量文件；本用例需要隔离该外部输入，
    # 才能稳定覆盖“无显式输入时读取 Git 失败”的分支。
    monkeypatch.delenv('QUALITY_CHANGED_FILES', raising=False)
    monkeypatch.setattr(
        language_policy,
        '_git_changed_files',
        lambda _root: (_ for _ in ()).throw(error),
    )

    result = language_policy.check([])

    assert result.status is CheckStatus.FAIL
    assert result.reason in {'input-unavailable', 'dependency-unavailable'}


def test_language_policy_finding_is_blocked(monkeypatch) -> None:
    """完整扫描发现英文叙述时继续返回 BLOCKED。"""
    monkeypatch.setattr(language_policy, '_run_check', lambda _root, _changed: ['policy violation'])

    assert language_policy.check([]).status is CheckStatus.BLOCKED
