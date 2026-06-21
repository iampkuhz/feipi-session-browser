"""session_browser.sources.jsonl_reader 的单元测试.

覆盖:
- 标准 JSONL(每行一个对象,全部成功)
- 含坏行的 JSONL(跳过坏行,收集诊断信息)
- 美化打印/多行 JSON 对象
- 混合 ``}{`` 拼接格式(过渡行)
- 空文件处理
- 诊断信息完整性(line_no,issue 类型,preview,severity)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from session_browser.sources.jsonl_reader import (
    JsonlDiagnostics,
    ParseIssue,
    ParseSeverity,
    _brace_chars_outside_strings,
    _build_diagnostics,
    _split_at_depth0,
    _try_parse_json,
    parse_jsonl_events,
)

EXPECTED_TWO_ITEMS = 2
EXPECTED_THREE_ITEMS = 3
LINE_TWO = 2
LINE_THREE = 3
LINE_FIVE = 5
LINE_SEVEN = 7
LINE_TEN = 10
LINE_FORTY_TWO = 42


# ─── 辅助函数 ─────────────────────────────────────────────────────────────


def _write(content: str) -> Path:
    """将 *content* 写入临时文件并返回其路径."""
    fd, path = tempfile.mkstemp(suffix='.jsonl')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(content)
    return Path(path)


# ─── 标准 JSONL ──────────────────────────────────────────────────────


class TestStandardJsonl:
    """每行一个 JSON 对象,全部可解析."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_single_object(self):
        p = _write('{"type": "message", "id": 1}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == 1
        assert events[0]['type'] == 'message'
        assert diag.events_parsed == 1
        assert diag.events_skipped == 0
        assert diag.error_count == 0
        assert diag.warning_count == 0

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_multiple_objects(self):
        lines = [
            '{"type": "start", "seq": 1}',
            '{"type": "delta", "seq": 2}',
            '{"type": "end", "seq": 3}',
        ]
        p = _write('\n'.join(lines) + '\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_THREE_ITEMS
        assert [e['type'] for e in events] == ['start', 'delta', 'end']
        assert diag.events_parsed == EXPECTED_THREE_ITEMS
        assert diag.events_skipped == 0

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_trailing_newline_ignored(self):
        p = _write('{"a": 1}\n\n{"b": 2}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert diag.non_empty_lines == EXPECTED_TWO_ITEMS

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_no_trailing_newline(self):
        p = _write('{"a": 1}\n{"b": 2}')
        events, _diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_string_path_accepted(self):
        p = _write('{"x": true}\n')
        events, _diag = parse_jsonl_events(str(p))
        assert len(events) == 1


# ─── 坏行/非对象值 ───────────────────────────────────────────────


class TestBadLines:
    """包含不可解析行或非 dict JSON 值的 JSONL."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_bad_json_line_skipped(self):
        p = _write('{"good": true}\n{bad json}\n{"also_good": 1}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert diag.events_skipped == 1
        assert diag.error_count == 1
        assert diag.warning_count == 0
        assert diag.issues[0].issue == ParseIssue.BAD_JSON
        assert diag.issues[0].severity == ParseSeverity.ERROR

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_non_object_skipped(self):
        lines = [
            '{"keep": "this"}',
            '["an", "array"]',
            '"just a string"',
            '42',
            '{"keep": "that"}',
        ]
        p = _write('\n'.join(lines) + '\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert diag.events_skipped == EXPECTED_THREE_ITEMS
        assert diag.warning_count == EXPECTED_THREE_ITEMS
        assert diag.error_count == 0
        skipped_issues = [i for i in diag.issues if i.issue == ParseIssue.NON_OBJECT_SKIPPED]
        assert len(skipped_issues) == EXPECTED_THREE_ITEMS

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_mixed_bad_and_non_object(self):
        p = _write('{"ok": 1}\nnot json at all\n[1, 2, 3]\n{"ok": 2}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert diag.events_skipped == EXPECTED_TWO_ITEMS
        assert diag.error_count == 1
        assert diag.warning_count == 1


# ─── 多行/美化打印 JSON ────────────────────────────────────────────


class TestMultiLineJson:
    """跨多行的美化打印 JSON."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_single_pretty_object(self):
        pretty = (
            '{\n'
            '  "type": "message",\n'
            '  "content": {\n'
            '    "text": "hello",\n'
            '    "role": "user"\n'
            '  }\n'
            '}\n'
        )
        p = _write(pretty)
        events, diag = parse_jsonl_events(p)
        assert len(events) == 1
        assert events[0]['type'] == 'message'
        assert events[0]['content']['text'] == 'hello'
        assert diag.events_parsed == 1
        assert diag.events_skipped == 0

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_two_pretty_objects(self):
        obj1 = '{\n  "id": 1\n}'
        obj2 = '{\n  "id": 2,\n  "extra": [\n    "a",\n    "b"\n  ]\n}'
        p = _write(obj1 + '\n' + obj2 + '\n')
        events, _diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert [event['id'] for event in events] == [1, 2]

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_pretty_with_string_containing_braces(self):
        """JSON 字符串中的花括号不得影响深度追踪."""
        pretty = '{\n  "key": "a{b}c",\n  "nested": {"x": 1}\n}\n'
        p = _write(pretty)
        events, _diag = parse_jsonl_events(p)
        assert len(events) == 1
        assert events[0]['key'] == 'a{b}c'


# ─── 混合 }{ 拼接格式 ──────────────────────────────────────────────


class TestConcatenatedObjects:
    """包含 ``}{...}{`` 拼接 JSON 的过渡行.

    解析器累积行直到深度回到 0.当累积文本包含多个
    顶层对象时检测到 ``}{`` 过渡.这发生在部分多行对象
    后面跟着一行同时关闭前一个对象并开始新对象时
    (例如深度 > 0 时出现 ``}{"b": 2}``).
    """

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_pretty_then_concatenated_transition(self):
        r"""多行对象在同一行关闭并拼接新对象.

        累积文本:``{\n  "a": 1\n}{"b": 2}``
        经 _split_at_depth0 分割后得到两个对象.
        """
        content = '{\n  "a": 1\n}{"b": 2}\n'
        p = _write(content)
        events, _diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert [events[0]['a'], events[1]['b']] == [1, 2]

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_pretty_then_two_concatenated(self):
        """多行对象后跟关闭行上的两个拼接对象."""
        content = '{\n  "a": 1\n}{"b": 2}{"c": 3}\n'
        p = _write(content)
        events, _diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_THREE_ITEMS
        assert [events[0]['a'], events[1]['b'], events[2]['c']] == [1, 2, 3]

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_concatenated_followed_by_standard_jsonl(self):
        """过渡行后面跟独立的标准 JSONL 行."""
        content = '{\n  "a": 1\n}{"b": 2}\n{"c": 3}\n'
        p = _write(content)
        events, _diag = parse_jsonl_events(p)
        assert len(events) == EXPECTED_THREE_ITEMS
        assert [events[0]['a'], events[1]['b'], events[2]['c']] == [1, 2, 3]

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_concatenated_non_object_in_split(self):
        """拼接分割产生非对象片段时记录为 BAD_JSON.

        当 ``}{`` 分割产生不可解析的片段时(因为
        拼接了非对象),它们作为 BAD_JSON 处理
        而非 NON_OBJECT_SKIPPED.
        """
        events: list = []
        skipped: list = []
        # 干净地拼接两个 dict
        _try_parse_json('{"a": 1}{"b": 2}', 5, events, skipped)
        assert len(events) == EXPECTED_TWO_ITEMS
        assert len(skipped) == 0

        # 通过 }{ 拼接 dict 和数字 —— 分割部分不可解析
        events2: list = []
        skipped2: list = []
        _try_parse_json('{"a": 1}}{42}', 7, events2, skipped2)
        assert len(events2) == 0
        assert len(skipped2) == 1
        assert skipped2[0][0] == LINE_SEVEN
        assert skipped2[0][1] == 'BAD_JSON'


# ─── 空文件 ─────────────────────────────────────────────────────────────


class TestEmptyFile:
    """空文件和纯空白文件应返回空结果,不崩溃."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_completely_empty_returns_empty(self):
        p = _write('')
        events, diagnostics = parse_jsonl_events(p)
        assert events == []
        assert diagnostics.events_parsed == 0
        assert diagnostics.error_count == 0

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_whitespace_only_returns_empty(self):
        p = _write('\n\n  \t\n')
        events, diagnostics = parse_jsonl_events(p)
        assert events == []
        assert diagnostics.events_parsed == 0
        assert diagnostics.error_count == 0


# ─── 诊断信息完整性 ────────────────────────────────────────────────────


class TestDiagnosticsCompleteness:
    """验证诊断信息携带所有必需字段."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_issue_has_line_no_detail_preview(self):
        content = '{"good": true}\n{broken}\n[1, 2]\n'
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert len(diag.issues) == EXPECTED_TWO_ITEMS

        bad = diag.issues[0]
        assert bad.line_no == LINE_TWO
        assert 'L2' not in bad.detail or 'line 2' in bad.detail
        assert len(bad.preview) > 0
        assert '{broken}' in bad.preview

        non_obj = diag.issues[1]
        assert non_obj.line_no == LINE_THREE
        assert 'list' in non_obj.detail.lower()

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_total_lines_reflects_file(self):
        """total_lines 应等于最后一行的行号."""
        content = 'a\nb\nc\n'
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert diag.total_lines == LINE_THREE

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_non_empty_lines_count(self):
        content = '{"a": 1}\n\n{"b": 2}\n\n'
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert diag.non_empty_lines == EXPECTED_TWO_ITEMS

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_verbose_mode_prints(self, capsys: pytest.CaptureFixture[str]):
        content = '{"ok": 1}\n[1, 2]\n'
        p = _write(content)
        parse_jsonl_events(p, verbose=True)
        captured = capsys.readouterr()
        assert 'skipped' in captured.out.lower()

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_warning_error_counts(self):
        content = '{"ok": 1}\n{"ok": 2}\nbad json\n"string"\nalso bad\n'
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert diag.warning_count == 1  # 一个非字典对象
        assert diag.error_count == EXPECTED_TWO_ITEMS  # 两行错误的 JSON


# ─── 内部辅助函数 ────────────────────────────────────────────────────────


class TestBraceCharsOutsideStrings:
    """验证 _brace_chars_outside_strings 正确忽略字符串中的花括号."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_simple_object(self):
        assert _brace_chars_outside_strings('{"a": 1}') == '{}'

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_braces_in_string_ignored(self):
        # {"key": "{value}"} 应只保留 {}
        result = _brace_chars_outside_strings('{"key": "{value}"}')
        assert result == '{}'

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_nested_braces(self):
        result = _brace_chars_outside_strings('{"a": {"b": [1, 2]}}')
        assert result == '{{[]}}'

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_escaped_quote(self):
        result = _brace_chars_outside_strings('{"key": "say \\"hi\\""}')
        # 转义引号不应切换 in_string 状态
        assert result == '{}'


class TestSplitAtDepth0:
    """验证 _split_at_depth0 正确分割拼接对象."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_no_split_needed(self):
        assert _split_at_depth0('{"a": 1}') == ['{"a": 1}']

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_two_concatenated(self):
        parts = _split_at_depth0('{"a": 1}{"b": 2}')
        assert len(parts) == EXPECTED_TWO_ITEMS
        assert parts[0] == '{"a": 1}'
        assert parts[1] == '{"b": 2}'

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_three_concatenated(self):
        parts = _split_at_depth0('{"a": 1}{"b": 2}{"c": 3}')
        assert len(parts) == EXPECTED_THREE_ITEMS

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_concatenated_with_nested(self):
        parts = _split_at_depth0('{"a": {"x": 1}}{"b": 2}')
        assert len(parts) == EXPECTED_TWO_ITEMS
        assert parts[0] == '{"a": {"x": 1}}'
        assert parts[1] == '{"b": 2}'

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_string_with_brace_not_split(self):
        # }{"k": "}{"}  -- 字符串内的 }{ 不应成为分割点
        parts = _split_at_depth0('{"k": "}{"}')
        assert parts == ['{"k": "}{"}']


class TestTryParseJson:
    """验证 _try_parse_json 正确路由事件与跳过项."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_valid_dict(self):
        events: list = []
        skipped: list = []
        _try_parse_json('{"a": 1}', 1, events, skipped)
        assert len(events) == 1
        assert len(skipped) == 0

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_valid_list_skipped(self):
        events: list = []
        skipped: list = []
        _try_parse_json('[1, 2]', 5, events, skipped)
        assert len(events) == 0
        assert len(skipped) == 1
        assert skipped[0][0] == LINE_FIVE
        assert skipped[0][1] == 'list'

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_bad_json_recorded(self):
        events: list = []
        skipped: list = []
        _try_parse_json('not json', 10, events, skipped)
        assert len(events) == 0
        assert len(skipped) == 1
        assert skipped[0][0] == LINE_TEN
        assert skipped[0][1] == 'BAD_JSON'


class TestBuildDiagnostics:
    """验证 _build_diagnostics 将跳过元组映射为 ParseIssueItem."""

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_bad_json_mapped(self):
        diag = JsonlDiagnostics()
        events: list = []
        skipped = [(42, 'BAD_JSON', "'bad'")]
        result = _build_diagnostics(diag, skipped, events)
        assert result.error_count == 1
        item = result.issues[0]
        assert item.line_no == LINE_FORTY_TWO
        assert item.issue == ParseIssue.BAD_JSON
        assert item.severity == ParseSeverity.ERROR

    @pytest.mark.contract_case('DATA-SOURCE-001')
    def test_non_object_mapped(self):
        diag = JsonlDiagnostics()
        events: list = []
        skipped = [(7, 'list', "'[1,2]'")]
        result = _build_diagnostics(diag, skipped, events)
        assert result.warning_count == 1
        item = result.issues[0]
        assert item.issue == ParseIssue.NON_OBJECT_SKIPPED
        assert item.severity == ParseSeverity.WARNING
        assert item.line_no == LINE_SEVEN
