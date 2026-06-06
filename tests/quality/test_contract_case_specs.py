from __future__ import annotations

from pathlib import Path

from scripts.quality.validate_acceptance_contracts import (
    EXPECTED_FEATURE_TABLES,
    validate_acceptance_contracts,
)


ROOT = Path(__file__).resolve().parents[2]
ACCEPTANCE_CONTRACTS = ROOT / "docs" / "acceptance-contracts"
DATA_PRESENTER_TABLE = (
    ACCEPTANCE_CONTRACTS / "features" / "DATA_PRESENTERS.md"
)
ROUND_SIGNALS_TEST = ROOT / "tests" / "backend" / "test_round_signals.py"


def test_acceptance_contract_feature_tables_are_restored() -> None:
    feature_dir = ACCEPTANCE_CONTRACTS / "features"
    actual = {path.name for path in feature_dir.glob("*.md")}

    assert EXPECTED_FEATURE_TABLES <= actual
    for filename in EXPECTED_FEATURE_TABLES:
        text = (feature_dir / filename).read_text(encoding="utf-8")
        assert text.count("|---") >= 2
        assert "| 项 | 内容 |" in text
        assert "## 契约用例" in text
        assert "| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 |" in text


def test_data_presenter_006_is_defined_in_current_spec() -> None:
    table_text = DATA_PRESENTER_TABLE.read_text(encoding="utf-8")
    test_text = ROUND_SIGNALS_TEST.read_text(encoding="utf-8")

    assert '@pytest.mark.contract_case("DATA-PRESENTER-006")' in test_text
    assert "| DATA-PRESENTER-006 |" in table_text
    assert "compute_round_signals" in table_text
    assert "tests/backend/test_round_signals.py" in table_text


def test_acceptance_contract_bindings_are_consistent() -> None:
    result = validate_acceptance_contracts(ROOT)
    assert result.errors == []


def test_orphan_test_marker_fails_when_contract_row_is_missing(tmp_path: Path) -> None:
    feature_dir = tmp_path / "docs" / "acceptance-contracts" / "features"
    tests_dir = tmp_path / "tests"
    orphan_id = "DATA-PRESENTER-" + "999"
    feature_dir.mkdir(parents=True)
    tests_dir.mkdir()

    template = """# Feature

## 范围

| 项 | 内容 |
|---|---|
| 模块 | test |

## 契约用例

| 用例 ID | 优先级 | 分层 | 场景 | 怎么测 | 必须断言 | 测试类型 | 关联检查 | 代码位置 |
|---|---:|---|---|---|---|---|---|---|
"""
    for filename in EXPECTED_FEATURE_TABLES:
        (feature_dir / filename).write_text(template, encoding="utf-8")

    (tests_dir / "test_orphan_marker.py").write_text(
        'import pytest\n\n'
        f'@pytest.mark.contract_case("{orphan_id}")\n'
        'def test_orphan_marker():\n'
        '    assert True\n',
        encoding="utf-8",
    )

    result = validate_acceptance_contracts(tmp_path)

    assert any(
        f"{orphan_id} 在测试代码中绑定，但 docs 契约表未定义" in error
        for error in result.errors
    )
