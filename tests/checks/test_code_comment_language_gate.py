#!/usr/bin/env python3
"""验证中文注释 Gate 的作用域、语言质量与诊断契约。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / 'scripts' / 'checks' / 'check_code_comment_language.py'
spec = importlib.util.spec_from_file_location('comment_checker', MODULE)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)
TERMS, FORBIDDEN = checker.load_policy(REPO_ROOT / 'config' / 'technical-terms.json')


def scan_python(tmp_path: Path, source: str) -> list[checker.Violation]:
    """写入最小 Python fixture 并返回结构化违规。"""
    path = tmp_path / 'tool.py'
    path.write_text(source, encoding='utf-8')
    return checker.check_python_file(path, TERMS, FORBIDDEN)


def scan_shell(tmp_path: Path, source: str, *, hook: bool = False) -> list[checker.Violation]:
    """写入最小 shell fixture；Hook 模式使用受约束包装器路径。"""
    parent = tmp_path / 'hooks' if hook else tmp_path
    parent.mkdir(exist_ok=True)
    path = parent / 'tool.sh'
    path.write_text(source, encoding='utf-8')
    return checker.check_shell_file(path, TERMS, FORBIDDEN)


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
    source = '''"""负责读取执行收据；不负责运行命令，由 Stop pipeline 调用。"""

def _load_receipt():
    return None
'''
    assert 'DEFINITION_DOCSTRING_MISSING' in codes(scan_python(tmp_path, source))


def test_module_contract_requires_responsibility_boundary_and_caller(tmp_path: Path) -> None:
    violations = scan_python(tmp_path, '"""中文工具。"""\n')
    assert 'MODULE_DOCSTRING_INCOMPLETE' in codes(violations)
    assert '职责、非职责、调用者' in violations[0].message


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
    source = '''"""负责校验 Stop Gate receipt；不负责执行 pipeline，由 Hook CLI 调用。"""

def validate_receipt():
    """读取 JSON receipt，并校验 SHA-256 与 worktree identity 一致。"""
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


def test_java_lexer_ignores_comment_markers_inside_strings(tmp_path: Path) -> None:
    path = tmp_path / 'Sample.java'
    path.write_text('class Sample { String value = "// English text"; }', encoding='utf-8')
    assert checker.extract(path) == []


def test_java_keeps_legacy_line_comment_threshold_and_term_mix() -> None:
    comment = checker.Comment('Sample.java', 7, 'line', '退出码：mismatch → 1，source error → 2')
    assert checker.check(comment, TERMS, FORBIDDEN) == []


def test_java_still_rejects_english_dominant_comment() -> None:
    comment = checker.Comment(
        'Sample.java', 7, 'line', 'Read cached execution result from local storage.'
    )
    assert 'COMMENT_NOT_CHINESE_DOMINANT' in codes(checker.check(comment, TERMS, FORBIDDEN))


def test_java_does_not_inherit_script_only_template_policy() -> None:
    comment = checker.Comment('Sample.java', 7, 'javadoc', '此对象表示 Sample 的来源信息。')
    assert checker.check(comment, TERMS, FORBIDDEN) == []


def test_filter_changed_paths_limits_roots() -> None:
    assert checker.filter_changed_paths(
        ['scripts', '.claude/hooks'],
        ['scripts/tool.py', '.claude/hooks/stop.sh', 'tests/test_tool.py'],
    ) == ['scripts/tool.py', '.claude/hooks/stop.sh']
