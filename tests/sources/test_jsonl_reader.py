"""Unit tests for session_browser.sources.jsonl_reader.

Covers:
- Standard JSONL (one object per line, all succeed)
- JSONL with bad lines (bad rows skipped, diagnostics collected)
- Pretty-printed / multi-line JSON objects
- Mixed ``}{`` concatenated format on transition lines
- Empty file handling
- Diagnostic completeness (line_no, issue type, preview, severity)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from session_browser.sources.jsonl_reader import (
    JsonlDiagnostics,
    ParseIssue,
    ParseIssueItem,
    ParseSeverity,
    _brace_chars_outside_strings,
    _build_diagnostics,
    _split_at_depth0,
    _try_parse_json,
    parse_jsonl_events,
)


# ─── Helpers ─────────────────────────────────────────────────────────────


def _write(content: str) -> Path:
    """Write *content* to a temporary file and return its Path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with open(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return Path(path)


# ─── Standard JSONL ──────────────────────────────────────────────────────


class TestStandardJsonl:
    """One JSON object per line, all parseable."""

    def test_single_object(self):
        p = _write('{"type": "message", "id": 1}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == 1
        assert events[0]["type"] == "message"
        assert diag.events_parsed == 1
        assert diag.events_skipped == 0
        assert diag.error_count == 0
        assert diag.warning_count == 0

    def test_multiple_objects(self):
        lines = [
            '{"type": "start", "seq": 1}',
            '{"type": "delta", "seq": 2}',
            '{"type": "end", "seq": 3}',
        ]
        p = _write("\n".join(lines) + "\n")
        events, diag = parse_jsonl_events(p)
        assert len(events) == 3
        assert [e["type"] for e in events] == ["start", "delta", "end"]
        assert diag.events_parsed == 3
        assert diag.events_skipped == 0

    def test_trailing_newline_ignored(self):
        p = _write('{"a": 1}\n\n{"b": 2}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2
        assert diag.non_empty_lines == 2

    def test_no_trailing_newline(self):
        p = _write('{"a": 1}\n{"b": 2}')
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2

    def test_string_path_accepted(self):
        p = _write('{"x": true}\n')
        events, diag = parse_jsonl_events(str(p))
        assert len(events) == 1


# ─── Bad lines / non-object values ───────────────────────────────────────


class TestBadLines:
    """JSONL containing unparseable lines or non-dict JSON values."""

    def test_bad_json_line_skipped(self):
        p = _write('{"good": true}\n{bad json}\n{"also_good": 1}\n')
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2
        assert diag.events_skipped == 1
        assert diag.error_count == 1
        assert diag.warning_count == 0
        assert diag.issues[0].issue == ParseIssue.BAD_JSON
        assert diag.issues[0].severity == ParseSeverity.ERROR

    def test_non_object_skipped(self):
        lines = [
            '{"keep": "this"}',
            '["an", "array"]',
            '"just a string"',
            '42',
            '{"keep": "that"}',
        ]
        p = _write("\n".join(lines) + "\n")
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2
        assert diag.events_skipped == 3
        assert diag.warning_count == 3
        assert diag.error_count == 0
        skipped_issues = [i for i in diag.issues
                          if i.issue == ParseIssue.NON_OBJECT_SKIPPED]
        assert len(skipped_issues) == 3

    def test_mixed_bad_and_non_object(self):
        p = _write(
            '{"ok": 1}\n'
            'not json at all\n'
            '[1, 2, 3]\n'
            '{"ok": 2}\n'
        )
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2
        assert diag.events_skipped == 2
        assert diag.error_count == 1
        assert diag.warning_count == 1


# ─── Multi-line / pretty-printed JSON ────────────────────────────────────


class TestMultiLineJson:
    """Pretty-printed JSON spanning multiple lines."""

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
        assert events[0]["type"] == "message"
        assert events[0]["content"]["text"] == "hello"
        assert diag.events_parsed == 1
        assert diag.events_skipped == 0

    def test_two_pretty_objects(self):
        obj1 = '{\n  "id": 1\n}'
        obj2 = '{\n  "id": 2,\n  "extra": [\n    "a",\n    "b"\n  ]\n}'
        p = _write(obj1 + "\n" + obj2 + "\n")
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2
        assert events[0]["id"] == 1
        assert events[1]["id"] == 2

    def test_pretty_with_string_containing_braces(self):
        """Braces inside JSON strings must not affect depth tracking."""
        pretty = (
            '{\n'
            '  "key": "a{b}c",\n'
            '  "nested": {"x": 1}\n'
            '}\n'
        )
        p = _write(pretty)
        events, diag = parse_jsonl_events(p)
        assert len(events) == 1
        assert events[0]["key"] == "a{b}c"


# ─── Mixed }{ concatenated format ───────────────────────────────────────


class TestConcatenatedObjects:
    """Transition lines containing ``}{...}{`` concatenated JSON.

    The parser accumulates lines until depth returns to 0.  A ``}{``
    transition is detected when the accumulated text contains multiple
    top-level objects.  This happens when a partial multi-line object
    is followed by a line that both closes the previous object AND
    starts new ones (e.g. ``}{"b": 2}`` while depth > 0).
    """

    def test_pretty_then_concatenated_transition(self):
        """Multi-line object closed on same line as concatenated new object.

        Accumulated text: ``{\n  "a": 1\n}{"b": 2}``
        After _split_at_depth0 -> two objects.
        """
        content = (
            '{\n'
            '  "a": 1\n'
            '}{"b": 2}\n'
        )
        p = _write(content)
        events, diag = parse_jsonl_events(p)
        assert len(events) == 2
        assert events[0]["a"] == 1
        assert events[1]["b"] == 2

    def test_pretty_then_two_concatenated(self):
        """Multi-line object followed by two concatenated objects on close line."""
        content = (
            '{\n'
            '  "a": 1\n'
            '}{"b": 2}{"c": 3}\n'
        )
        p = _write(content)
        events, diag = parse_jsonl_events(p)
        assert len(events) == 3
        assert events[0]["a"] == 1
        assert events[1]["b"] == 2
        assert events[2]["c"] == 3

    def test_concatenated_followed_by_standard_jsonl(self):
        """Transition line followed by independent standard JSONL lines."""
        content = (
            '{\n'
            '  "a": 1\n'
            '}{"b": 2}\n'
            '{"c": 3}\n'
        )
        p = _write(content)
        events, diag = parse_jsonl_events(p)
        assert len(events) == 3
        assert events[0]["a"] == 1
        assert events[1]["b"] == 2
        assert events[2]["c"] == 3

    def test_concatenated_non_object_in_split(self):
        """A concatenated line containing non-objects is recorded as BAD_JSON.

        When ``}{`` splits yield non-parseable fragments (because a
        non-object is concatenated), they fall through as BAD_JSON
        rather than NON_OBJECT_SKIPPED.
        """
        events: list = []
        skipped: list = []
        # Clean two dicts concatenated
        _try_parse_json('{"a": 1}{"b": 2}', 5, events, skipped)
        assert len(events) == 2
        assert len(skipped) == 0

        # Dict followed by a number via }{ -- the split part is unparseable
        events2: list = []
        skipped2: list = []
        _try_parse_json('{"a": 1}}{42}', 7, events2, skipped2)
        assert len(events2) == 0
        assert len(skipped2) == 1
        assert skipped2[0][0] == 7
        assert skipped2[0][1] == "BAD_JSON"


# ─── Empty file ──────────────────────────────────────────────────────────


class TestEmptyFile:
    """Empty and whitespace-only files should return empty results, not crash."""

    def test_completely_empty_returns_empty(self):
        p = _write("")
        events, diagnostics = parse_jsonl_events(p)
        assert events == []
        assert diagnostics.events_parsed == 0
        assert diagnostics.error_count == 0

    def test_whitespace_only_returns_empty(self):
        p = _write("\n\n  \t\n")
        events, diagnostics = parse_jsonl_events(p)
        assert events == []
        assert diagnostics.events_parsed == 0
        assert diagnostics.error_count == 0


# ─── Diagnostics completeness ────────────────────────────────────────────


class TestDiagnosticsCompleteness:
    """Verify that diagnostics carry all required fields."""

    def test_issue_has_line_no_detail_preview(self):
        content = (
            '{"good": true}\n'
            '{broken}\n'
            '[1, 2]\n'
        )
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert len(diag.issues) == 2

        bad = diag.issues[0]
        assert bad.line_no == 2
        assert "L2" not in bad.detail or "line 2" in bad.detail
        assert len(bad.preview) > 0
        assert "{broken}" in bad.preview

        non_obj = diag.issues[1]
        assert non_obj.line_no == 3
        assert "list" in non_obj.detail.lower()

    def test_total_lines_reflects_file(self):
        """total_lines should equal the last line number seen."""
        content = "a\nb\nc\n"
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert diag.total_lines == 3

    def test_non_empty_lines_count(self):
        content = '{"a": 1}\n\n{"b": 2}\n\n'
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert diag.non_empty_lines == 2

    def test_verbose_mode_prints(self, capsys):
        content = '{"ok": 1}\n[1, 2]\n'
        p = _write(content)
        parse_jsonl_events(p, verbose=True)
        captured = capsys.readouterr()
        assert "skipped" in captured.out.lower()

    def test_warning_error_counts(self):
        content = (
            '{"ok": 1}\n'
            '{"ok": 2}\n'
            'bad json\n'
            '"string"\n'
            'also bad\n'
        )
        p = _write(content)
        _, diag = parse_jsonl_events(p)
        assert diag.warning_count == 1   # one non-dict
        assert diag.error_count == 2     # two bad json lines


# ─── Internal helpers ────────────────────────────────────────────────────


class TestBraceCharsOutsideStrings:
    """Verify _brace_chars_outside_strings correctly ignores braces in strings."""

    def test_simple_object(self):
        assert _brace_chars_outside_strings('{"a": 1}') == "{}"

    def test_braces_in_string_ignored(self):
        # {"key": "{value}"} should yield only {}
        result = _brace_chars_outside_strings('{"key": "{value}"}')
        assert result == "{}"

    def test_nested_braces(self):
        result = _brace_chars_outside_strings('{"a": {"b": [1, 2]}}')
        assert result == "{{[]}}"

    def test_escaped_quote(self):
        result = _brace_chars_outside_strings('{"key": "say \\"hi\\""}')
        # Escaped quotes should not toggle in_string state
        assert result == "{}"


class TestSplitAtDepth0:
    """Verify _split_at_depth0 splits concatenated objects."""

    def test_no_split_needed(self):
        assert _split_at_depth0('{"a": 1}') == ['{"a": 1}']

    def test_two_concatenated(self):
        parts = _split_at_depth0('{"a": 1}{"b": 2}')
        assert len(parts) == 2
        assert parts[0] == '{"a": 1}'
        assert parts[1] == '{"b": 2}'

    def test_three_concatenated(self):
        parts = _split_at_depth0('{"a": 1}{"b": 2}{"c": 3}')
        assert len(parts) == 3

    def test_concatenated_with_nested(self):
        parts = _split_at_depth0('{"a": {"x": 1}}{"b": 2}')
        assert len(parts) == 2
        assert parts[0] == '{"a": {"x": 1}}'
        assert parts[1] == '{"b": 2}'

    def test_string_with_brace_not_split(self):
        # }{"k": "}{"}  -- the }{ inside string should not be a split point
        parts = _split_at_depth0('{"k": "}{"}')
        assert parts == ['{"k": "}{"}']


class TestTryParseJson:
    """Verify _try_parse_json routes events vs skipped correctly."""

    def test_valid_dict(self):
        events: list = []
        skipped: list = []
        _try_parse_json('{"a": 1}', 1, events, skipped)
        assert len(events) == 1
        assert len(skipped) == 0

    def test_valid_list_skipped(self):
        events: list = []
        skipped: list = []
        _try_parse_json('[1, 2]', 5, events, skipped)
        assert len(events) == 0
        assert len(skipped) == 1
        assert skipped[0][0] == 5
        assert skipped[0][1] == "list"

    def test_bad_json_recorded(self):
        events: list = []
        skipped: list = []
        _try_parse_json('not json', 10, events, skipped)
        assert len(events) == 0
        assert len(skipped) == 1
        assert skipped[0][0] == 10
        assert skipped[0][1] == "BAD_JSON"


class TestBuildDiagnostics:
    """Verify _build_diagnostics maps skipped tuples to ParseIssueItems."""

    def test_bad_json_mapped(self):
        diag = JsonlDiagnostics()
        events: list = []
        skipped = [(42, "BAD_JSON", "'bad'")]
        result = _build_diagnostics(diag, skipped, events)
        assert result.error_count == 1
        item = result.issues[0]
        assert item.line_no == 42
        assert item.issue == ParseIssue.BAD_JSON
        assert item.severity == ParseSeverity.ERROR

    def test_non_object_mapped(self):
        diag = JsonlDiagnostics()
        events: list = []
        skipped = [(7, "list", "'[1,2]'")]
        result = _build_diagnostics(diag, skipped, events)
        assert result.warning_count == 1
        item = result.issues[0]
        assert item.issue == ParseIssue.NON_OBJECT_SKIPPED
        assert item.severity == ParseSeverity.WARNING
        assert item.line_no == 7
