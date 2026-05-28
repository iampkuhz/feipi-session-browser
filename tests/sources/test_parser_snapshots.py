"""parser 输出的快照测试，对照 fixture 语料库。

``tests/fixtures/sources/`` 中的每个 fixture JSONL 文件都有对应的
``.expected.json``，记录了标准的 parser 输出。这些测试验证
``parse_jsonl_events`` 产生的事件和诊断信息与存储的快照一致。

覆盖：
- 全部 6 个 fixture 文件：claude_valid、codex_valid、qoder_valid、
  multiline_json、empty、mixed_with_bad
- 事件列表一致性（内容 + 顺序）
- 诊断计数器：total_lines、non_empty_lines、events_parsed、events_skipped
- 诊断问题：问题类型、严重级别、行号、详情、预览
"""

from __future__ import annotations

import pytest
import json
from pathlib import Path

from session_browser.sources.jsonl_reader import (
    ParseIssue,
    ParseSeverity,
    parse_jsonl_events,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sources"

# 自动发现所有 fixture 对。
FIXTURE_PAIRS = sorted(
    p.stem for p in FIXTURES_DIR.glob("*.jsonl")
)


def _serialize_issue(issue_item) -> dict:
    """将 ParseIssueItem 转换为 expected 文件中使用的序列化字典格式。"""
    return {
        "issue": issue_item.issue.value,
        "severity": issue_item.severity.name,
        "line_no": issue_item.line_no,
        "detail": issue_item.detail,
        "preview": issue_item.preview,
    }


def _serialize_diagnostics(diag) -> dict:
    """将 JsonlDiagnostics 转换为 expected 文件中使用的序列化字典格式。"""
    return {
        "total_lines": diag.total_lines,
        "non_empty_lines": diag.non_empty_lines,
        "events_parsed": diag.events_parsed,
        "events_skipped": diag.events_skipped,
        "issues": [_serialize_issue(i) for i in diag.issues],
    }


def _build_actual(jsonl_path: Path) -> dict:
    """在 fixture 上运行 parser 并返回序列化结果。"""
    events, diagnostics = parse_jsonl_events(jsonl_path)
    return {
        "source_file": jsonl_path.name,
        "events": events,
        "diagnostics": _serialize_diagnostics(diagnostics),
    }


def _load_expected(name: str) -> dict:
    """加载 fixture 的预期快照。"""
    expected_path = FIXTURES_DIR / f"{name}.expected.json"
    with open(expected_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("fixture_name", FIXTURE_PAIRS)
class TestParserSnapshots:
    """基于快照的测试，将 parser 输出与预期 fixtures 对比。"""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_events_match(self, fixture_name: str):
        """解析的事件必须与预期快照完全匹配。"""
        jsonl_path = FIXTURES_DIR / f"{fixture_name}.jsonl"
        actual = _build_actual(jsonl_path)
        expected = _load_expected(fixture_name)

        assert actual["events"] == expected["events"], (
            f"Events mismatch for {fixture_name}:\n"
            f"  actual count:   {len(actual['events'])}\n"
            f"  expected count: {len(expected['events'])}"
        )

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_diagnostics_counters_match(self, fixture_name: str):
        """诊断计数器必须与预期快照一致。"""
        jsonl_path = FIXTURES_DIR / f"{fixture_name}.jsonl"
        actual = _build_actual(jsonl_path)
        expected = _load_expected(fixture_name)

        actual_diag = actual["diagnostics"]
        expected_diag = expected["diagnostics"]

        counter_keys = [
            "total_lines", "non_empty_lines",
            "events_parsed", "events_skipped",
        ]
        for key in counter_keys:
            assert actual_diag[key] == expected_diag[key], (
                f"Counter '{key}' mismatch for {fixture_name}: "
                f"actual={actual_diag[key]}, expected={expected_diag[key]}"
            )

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_diagnostics_issues_match(self, fixture_name: str):
        """诊断问题列表必须与预期快照一致。"""
        jsonl_path = FIXTURES_DIR / f"{fixture_name}.jsonl"
        actual = _build_actual(jsonl_path)
        expected = _load_expected(fixture_name)

        actual_issues = actual["diagnostics"]["issues"]
        expected_issues = expected["diagnostics"]["issues"]

        assert len(actual_issues) == len(expected_issues), (
            f"Issue count mismatch for {fixture_name}: "
            f"actual={len(actual_issues)}, expected={len(expected_issues)}"
        )

        for idx, (act, exp) in enumerate(zip(actual_issues, expected_issues)):
            assert act == exp, (
                f"Issue #{idx} mismatch for {fixture_name}:\n"
                f"  actual:   {act}\n"
                f"  expected: {exp}"
            )
