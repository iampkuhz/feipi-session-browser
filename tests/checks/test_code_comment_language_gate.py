#!/usr/bin/env python3
"""验证中文注释 Gate 的作用域、语言质量与诊断契约。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / 'scripts' / 'checks' / 'source' / 'check_code_comment_language.py'
spec = importlib.util.spec_from_file_location('comment_checker', MODULE)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)
TERMS, FORBIDDEN = checker._load_policy(REPO_ROOT / 'config' / 'technical-terms.json')


def scan_python(tmp_path: Path, source: str) -> list[checker.Violation]:
    """写入最小 Python fixture 并返回结构化违规。"""
    path = tmp_path / 'tool.py'
    path.write_text(source, encoding='utf-8')
    return checker._check_python_file(path, TERMS, FORBIDDEN)


def scan_check_leaf(tmp_path: Path, source: str) -> list[checker.Violation]:
    """写入统一协议的领域 Check fixture。"""
    path = tmp_path / 'scripts' / 'checks' / 'source' / 'check_sample.py'
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding='utf-8')
    return checker._check_python_file(path, TERMS, FORBIDDEN)


def scan_shell(tmp_path: Path, source: str, *, hook: bool = False) -> list[checker.Violation]:
    """写入最小 shell fixture；Hook 模式使用受约束包装器路径。"""
    parent = tmp_path / 'hooks' if hook else tmp_path
    parent.mkdir(exist_ok=True)
    path = parent / 'tool.sh'
    path.write_text(source, encoding='utf-8')
    return checker._check_shell_file(path, TERMS, FORBIDDEN)


def codes(violations: list[checker.Violation]) -> set[str]:
    """提取诊断代码，避免测试依赖输出顺序。"""
    return {item.code for item in violations}


def test_standard_python_docstring_is_the_public_contract(tmp_path: Path) -> None:
    source = '''"""负责构造确定性检查计划；不负责执行命令，由 Gate CLI 调用。"""

def build_plan(paths: list[str]) -> tuple[str, ...]:
    """按稳定顺序生成待执行目标；输入为空时返回空计划。"""
    return tuple(sorted(paths))

def _join(value: str) -> str:
    return value
'''
    assert scan_python(tmp_path, source) == []


def test_public_definition_requires_docstring_but_simple_private_does_not(tmp_path: Path) -> None:
    source = '''"""负责解析检查输入；不负责写文件，由命令行入口调用。"""

def public_api():
    return True

def _helper():
    return True
'''
    violations = scan_python(tmp_path, source)
    assert codes(violations) == {'DEFINITION_DOCSTRING_MISSING'}
    assert violations[0].preview == 'public_api'


def test_safety_critical_private_requires_docstring(tmp_path: Path) -> None:
    source = '''"""负责读取执行摘要；不负责运行命令，由 Stop pipeline 调用。"""

def _load_gate_summary():
    return None
'''
    assert 'DEFINITION_DOCSTRING_MISSING' in codes(scan_python(tmp_path, source))


def test_module_contract_requires_responsibility_boundary_and_caller(tmp_path: Path) -> None:
    violations = scan_python(tmp_path, '"""中文工具。"""\n')
    assert 'MODULE_DOCSTRING_INCOMPLETE' in codes(violations)
    assert '职责、非职责、调用者' in violations[0].message


def test_check_leaf_module_contract_explains_rule_entry_and_failure(tmp_path: Path) -> None:
    source = '''"""检查示例配置是否包含必需字段。

这项检查用于防止无效配置进入仓库。公开入口是 `check(arguments)`；返回诊断表示配置缺失。
"""

def check(arguments: list[str]) -> object:
    """检查传入配置。"""
    return object()
'''
    assert scan_check_leaf(tmp_path, source) == []


def test_check_leaf_module_contract_rejects_architecture_only_description(tmp_path: Path) -> None:
    source = '''"""检查示例配置。

公开入口是 `check(arguments)`。
"""
'''
    violation = next(
        item
        for item in scan_check_leaf(tmp_path, source)
        if item.code == 'MODULE_DOCSTRING_INCOMPLETE'
    )
    assert '存在原因' in violation.message
    assert '失败含义' in violation.message


@pytest.mark.parametrize(
    'phrase',
    [
        '当前函数使用的输入参数',
        '当前函数的计算结果',
        'Computed 结果',
        'output 参数',
        '维护 project Python cached',
        '表示 Sample。',
        '维护 load 函数行为',
    ],
)
def test_low_information_templates_fail(tmp_path: Path, phrase: str) -> None:
    source = f'''"""负责执行检查；不负责修改数据，由 Gate CLI 调用。"""

def run_check():
    """{phrase}。"""
    return True
'''
    assert 'COMMENT_LOW_INFORMATION' in codes(scan_python(tmp_path, source))


def test_english_dominant_and_mechanical_mixed_language_fail(tmp_path: Path) -> None:
    english = '''"""负责运行检查；不负责修改数据，由 Gate CLI 调用。"""

def run_check():
    """Read cached execution result from local storage."""
    return True
'''
    mixed = english.replace(
        'Read cached execution result from local storage.',
        '说明：Read cached execution result from local storage.',
    )
    assert 'COMMENT_NOT_CHINESE_DOMINANT' in codes(scan_python(tmp_path, english))
    assert 'COMMENT_MECHANICAL_MIXED_LANGUAGE' in codes(scan_python(tmp_path, mixed))


def test_canonical_technical_terms_do_not_dilute_chinese(tmp_path: Path) -> None:
    source = '''"""负责校验 Stop Gate artifact；不负责执行 pipeline，由 Hook CLI 调用。"""

def validate_artifact():
    """读取 JSON artifact，并校验 SHA-256 与本次执行信息一致。"""
    return True
'''
    assert scan_python(tmp_path, source) == []


def test_forbidden_translation_has_actionable_diagnostic(tmp_path: Path) -> None:
    source = '''"""负责执行检查；不负责修改数据，由 Gate CLI 调用。"""
# 使用爪哇实现边界检查。
'''
    violation = next(
        item for item in scan_python(tmp_path, source) if item.code == 'TECH_TERM_NOT_CANONICAL'
    )
    assert violation.line == 2
    assert violation.path.endswith('tool.py')
    assert violation.message
    assert 'canonical_terms' in violation.suggestion


def test_hook_wrapper_requires_chinese_delegation_boundary(tmp_path: Path) -> None:
    missing = '#!/usr/bin/env bash\nset -euo pipefail\nexec python3 -m tool\n'
    assert 'HOOK_WRAPPER_DOC_MISSING' in codes(scan_shell(tmp_path, missing, hook=True))
    documented = (
        '#!/usr/bin/env bash\n'
        '# 平台 Hook 调用此包装器；它只把 payload 委托给共享 runtime，不实现事件策略。\n'
        'set -euo pipefail\nexec python3 -m tool\n'
    )
    assert scan_shell(tmp_path, documented, hook=True) == []


def test_public_check_accepts_valid_script(tmp_path: Path) -> None:
    """公开入口直接扫描显式路径，合法源码不产生诊断。"""
    source = tmp_path / 'tool.py'
    source.write_text(
        '"""负责读取检查输入；不负责写入数据，由 Gate CLI 调用。"""\n',
        encoding='utf-8',
    )

    assert checker.check(
        [str(source), '--policy', str(REPO_ROOT / 'config/technical-terms.json')]
    ).passed


def test_public_check_reports_comment_violation(tmp_path: Path) -> None:
    """公开入口返回带路径和规则代码的可定位诊断。"""
    source = tmp_path / 'tool.py'
    source.write_text(
        '"""负责读取检查输入；不负责写入数据，由 Gate CLI 调用。"""\n'
        '# Run migration command from local cache.\n',
        encoding='utf-8',
    )

    result = checker.check(
        [str(source), '--policy', str(REPO_ROOT / 'config/technical-terms.json')]
    )

    assert not result.passed
    messages = [diagnostic.message for diagnostic in result.diagnostics]
    assert all(str(source) in message for message in messages)
    assert any('COMMENT_NOT_CHINESE_DOMINANT' in message for message in messages)


@pytest.mark.parametrize('policy_state', ['missing', 'invalid'])
def test_public_check_fails_closed_for_invalid_policy(tmp_path: Path, policy_state: str) -> None:
    """集中策略缺失或 JSON 无效时，公开入口必须返回失败而不是跳过检查。"""
    policy = tmp_path / 'policy.json'
    if policy_state == 'invalid':
        policy.write_text('{not-json', encoding='utf-8')

    result = checker.check(['--policy', str(policy)])

    assert not result.passed
    expected = 'POLICY_UNAVAILABLE' if policy_state == 'missing' else 'POLICY_INVALID'
    assert expected in result.diagnostics[0].message
    assert result.status.value == ('FAIL' if policy_state == 'missing' else 'BLOCKED')


@pytest.mark.parametrize(
    'legacy_option',
    [
        '--jobs',
        '--json-report',
        '--cache',
        '--files-from',
        '--script-comments',
        '--changed-files-env',
    ],
)
def test_public_check_rejects_removed_legacy_options(legacy_option: str) -> None:
    """已删除的并发、缓存和增量参数不得继续形成隐藏兼容入口。"""
    with pytest.raises(SystemExit):
        checker.check([legacy_option])
