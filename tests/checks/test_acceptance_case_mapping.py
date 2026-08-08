from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from scripts.gates.checks.repository.check_acceptance_case_mapping import (
    EXPECTED_FEATURE_TABLES,
    _validate_acceptance_case_mapping,
)

_TABLE_HEADER = """# Feature

## 验收用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
"""


def _write_minimum_tables(root: Path, extra_row: str = '') -> None:
    feature_dir = root / 'docs' / 'acceptance-cases' / 'features'
    feature_dir.mkdir(parents=True)
    for index, filename in enumerate(sorted(EXPECTED_FEATURE_TABLES)):
        suffix = extra_row if index == 0 else ''
        (feature_dir / filename).write_text(_TABLE_HEADER + suffix, encoding='utf-8')


def test_mapping_accepts_defined_case_with_existing_code_binding(tmp_path: Path) -> None:
    tests_dir = tmp_path / 'tests'
    tests_dir.mkdir()
    code_path = 'tests/test_feature.py'
    case_id = 'DATA-INDEX-' + '901'
    _write_minimum_tables(
        tmp_path,
        f'| {case_id} | P1 | unit | read | pytest | value | auto | gate | {code_path} |\n',
    )
    (tmp_path / code_path).write_text(f'# {case_id}\ndef test_value(): assert True\n')

    result = _validate_acceptance_case_mapping(tmp_path)

    assert result.errors == []


def test_mapping_rejects_test_id_missing_from_case_tables(tmp_path: Path) -> None:
    tests_dir = tmp_path / 'tests'
    tests_dir.mkdir()
    _write_minimum_tables(tmp_path)
    orphan_id = 'DATA-INDEX-' + '999'
    (tests_dir / 'test_orphan.py').write_text(f'# {orphan_id}\n', encoding='utf-8')

    result = _validate_acceptance_case_mapping(tmp_path)

    assert any(orphan_id in error and '验收用例表未定义' in error for error in result.errors)


def test_mapping_uses_current_acceptance_cases_directory(tmp_path: Path) -> None:
    (tmp_path / 'tests').mkdir()
    old_directory = 'acceptance-' + 'contracts'
    (tmp_path / 'docs' / old_directory / 'features').mkdir(parents=True)

    result = _validate_acceptance_case_mapping(tmp_path)

    assert any('acceptance-cases' in error and '目录不存在' in error for error in result.errors)
