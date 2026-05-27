"""Parser compatibility regression tests.

Verifies that the three adapter modules (claude, codex, qoder) expose
callable public function signatures, handle their respective fixture
corpora correctly, return properly-typed values, and gracefully tolerate
bad JSON and empty files without raising uncaught exceptions.

Coverage:
1. Public function signatures are importable and callable.
2. Each adapter handles its fixture corpus JSONL type.
3. Return value types match contracts (events: list[dict],
   diagnostics: JsonlDiagnostics, summary: SessionSummary).
4. Bad JSON lines do not cause uncaught exceptions.
5. Empty JSONL files do not cause uncaught exceptions.
"""

from __future__ import annotations

import pytest
import inspect
import json
import tempfile
from pathlib import Path
from typing import Callable

# ─── Shared types ────────────────────────────────────────────────────────

from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall
from session_browser.sources.jsonl_reader import (
    JsonlDiagnostics,
    parse_jsonl_events,
)

# ─── Fixture helpers ─────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sources"


def _write_jsonl(content: str) -> Path:
    """Write *content* to a temporary .jsonl file and return its Path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with open(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return Path(path)


# ─── 1. Public function signatures are callable ──────────────────────────


class TestPublicSignatures:
    """Verify that each adapter's public API is importable and callable."""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_parse_history_callable(self):
        from session_browser.sources import claude
        assert callable(claude.parse_history)
        sig = inspect.signature(claude.parse_history)
        assert isinstance(sig, inspect.Signature)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_parse_session_detail_callable(self):
        from session_browser.sources import claude
        assert callable(claude.parse_session_detail)
        sig = inspect.signature(claude.parse_session_detail)
        params = list(sig.parameters.keys())
        assert "project_key" in params
        assert "session_id" in params

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_parse_session_index_callable(self):
        from session_browser.sources import codex
        assert callable(codex.parse_session_index)
        sig = inspect.signature(codex.parse_session_index)
        assert isinstance(sig, inspect.Signature)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_read_threads_db_callable(self):
        from session_browser.sources import codex
        assert callable(codex.read_threads_db)
        sig = inspect.signature(codex.read_threads_db)
        assert isinstance(sig, inspect.Signature)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_parse_session_detail_callable(self):
        from session_browser.sources import codex
        assert callable(codex.parse_session_detail)
        sig = inspect.signature(codex.parse_session_detail)
        params = list(sig.parameters.keys())
        assert "session_id" in params

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_qoder_parse_session_detail_callable(self):
        from session_browser.sources import qoder
        assert callable(qoder.parse_session_detail)
        sig = inspect.signature(qoder.parse_session_detail)
        params = list(sig.parameters.keys())
        assert "project_key" in params
        assert "session_id" in params

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_qoder_normalize_timestamp_callable(self):
        from session_browser.sources import qoder
        assert callable(qoder.normalize_timestamp)
        sig = inspect.signature(qoder.normalize_timestamp)
        assert isinstance(sig, inspect.Signature)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_jsonl_reader_parse_jsonl_events_callable(self):
        assert callable(parse_jsonl_events)
        sig = inspect.signature(parse_jsonl_events)
        params = list(sig.parameters.keys())
        assert "path" in params
        assert "verbose" in params


# ─── 2. Adapter fixture corpus compatibility ─────────────────────────────


class TestFixtureCorpusCompatibility:
    """Each adapter must handle its fixture corpus without errors."""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_fixture_parses(self):
        """Claude-style JSONL fixture must parse into events + diagnostics."""
        jsonl_path = FIXTURES_DIR / "claude_valid.jsonl"
        assert jsonl_path.exists(), f"Fixture not found: {jsonl_path}"
        events, diag = parse_jsonl_events(jsonl_path)
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(ev, dict) for ev in events)
        assert isinstance(diag, JsonlDiagnostics)
        assert diag.events_parsed == len(events)

        # Claude fixtures have user and assistant types
        types = {ev.get("type") for ev in events}
        assert "user" in types
        assert "assistant" in types

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_fixture_parses(self):
        """Codex-style JSONL fixture must parse into events + diagnostics."""
        jsonl_path = FIXTURES_DIR / "codex_valid.jsonl"
        assert jsonl_path.exists(), f"Fixture not found: {jsonl_path}"
        events, diag = parse_jsonl_events(jsonl_path)
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(ev, dict) for ev in events)
        assert isinstance(diag, JsonlDiagnostics)
        assert diag.events_parsed == len(events)

        # Codex fixtures have message, tool_call, tool_result types
        types = {ev.get("type") for ev in events}
        assert "message" in types
        assert "tool_call" in types
        assert "tool_result" in types

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_qoder_fixture_parses(self):
        """Qoder-style JSONL fixture must parse into events + diagnostics."""
        jsonl_path = FIXTURES_DIR / "qoder_valid.jsonl"
        assert jsonl_path.exists(), f"Fixture not found: {jsonl_path}"
        events, diag = parse_jsonl_events(jsonl_path)
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(ev, dict) for ev in events)
        assert isinstance(diag, JsonlDiagnostics)
        assert diag.events_parsed == len(events)

        # Qoder fixtures have user and assistant types (Claude-like format)
        types = {ev.get("type") for ev in events}
        assert "user" in types
        assert "assistant" in types


# ─── 3. Return value type contracts ──────────────────────────────────────


class TestReturnValueContracts:
    """Verify that return types and structures match the expected contracts."""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_parse_jsonl_events_returns_list_of_dict(self):
        """parse_jsonl_events must return (list[dict], JsonlDiagnostics)."""
        p = _write_jsonl(
            '{"type": "user", "message": {"role": "user", "content": "hello"}}\n'
            '{"type": "assistant", "message": {"role": "assistant", "content": []}}\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            assert isinstance(events, list)
            assert all(isinstance(e, dict) for e in events)
            assert isinstance(diag, JsonlDiagnostics)
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_jsonl_diagnostics_has_required_fields(self):
        """JsonlDiagnostics must expose the expected fields."""
        p = _write_jsonl(
            '{"type": "user"}\n'
            'bad json\n'
            '["array"]\n'
        )
        try:
            _, diag = parse_jsonl_events(p)
            # Required numeric fields
            assert isinstance(diag.total_lines, int)
            assert isinstance(diag.non_empty_lines, int)
            assert isinstance(diag.events_parsed, int)
            assert isinstance(diag.events_skipped, int)
            # Required computed properties
            assert isinstance(diag.warning_count, int)
            assert isinstance(diag.error_count, int)
            # Required list field
            assert isinstance(diag.issues, list)
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_parse_session_detail_returns_correct_types(self):
        """parse_session_detail must return (SessionSummary, list[ChatMessage],
        list[ToolCall], list[dict]) for claude adapter."""
        from session_browser.sources import claude

        valid_events = [
            {"type": "user", "message": {"role": "user", "content": "hello"},
             "timestamp": "2026-05-02T00:00:00.000Z", "cwd": "/test",
             "entrypoint": "cli", "gitBranch": "main"},
            {"type": "assistant", "message": {"id": "msg-1", "model": "test",
             "role": "assistant", "content": [{"type": "text", "text": "hi"}],
             "usage": {"input_tokens": 10, "output_tokens": 5},
             "stop_reason": "end_turn"},
             "timestamp": "2026-05-02T00:00:01.000Z"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            original = claude.CLAUDE_DATA_DIR
            claude.CLAUDE_DATA_DIR = Path(tmpdir)
            try:
                project_dir = Path(tmpdir) / "projects" / "test-proj"
                project_dir.mkdir(parents=True)
                session_file = project_dir / "sid-001.jsonl"
                session_file.write_text(
                    "\n".join(json.dumps(e) for e in valid_events),
                    encoding="utf-8",
                )

                summary, messages, tool_calls, subagent_runs = (
                    claude.parse_session_detail("test-proj", "sid-001")
                )

                assert isinstance(summary, SessionSummary)
                assert summary.agent == "claude_code"
                assert isinstance(messages, list)
                assert all(isinstance(m, ChatMessage) for m in messages)
                assert isinstance(tool_calls, list)
                assert all(isinstance(tc, ToolCall) for tc in tool_calls)
                assert isinstance(subagent_runs, list)
            finally:
                claude.CLAUDE_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_parse_session_detail_returns_correct_types(self):
        """parse_session_detail must return (SessionSummary, list[ChatMessage],
        list[ToolCall], list[dict]) for codex adapter."""
        from session_browser.sources import codex

        with tempfile.TemporaryDirectory() as tmpdir:
            original = codex.CODEX_DATA_DIR
            codex.CODEX_DATA_DIR = Path(tmpdir)
            try:
                summary, messages, tool_calls, subagent_runs = (
                    codex.parse_session_detail("nonexistent-session")
                )

                assert isinstance(summary, SessionSummary)
                assert summary.agent == "codex"
                assert isinstance(messages, list)
                assert isinstance(tool_calls, list)
                assert isinstance(subagent_runs, list)
            finally:
                codex.CODEX_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_qoder_parse_session_detail_returns_correct_types(self):
        """parse_session_detail must return (SessionSummary, list[ChatMessage],
        list[ToolCall], list[dict]) for qoder adapter."""
        from session_browser.sources import qoder

        with tempfile.TemporaryDirectory() as tmpdir:
            original = qoder.QODER_DATA_DIR
            qoder.QODER_DATA_DIR = Path(tmpdir)
            try:
                summary, messages, tool_calls, subagent_runs = (
                    qoder.parse_session_detail("test-proj", "nonexistent-session")
                )

                assert isinstance(summary, SessionSummary)
                assert summary.agent == "qoder"
                assert isinstance(messages, list)
                assert isinstance(tool_calls, list)
                assert isinstance(subagent_runs, list)
            finally:
                qoder.QODER_DATA_DIR = original


# ─── 4. Bad JSON tolerance ───────────────────────────────────────────────


class TestBadJsonTolerance:
    """Bad JSON must not raise uncaught exceptions."""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_completely_unparseable_lines(self):
        """Lines that are not valid JSON at all must be silently skipped."""
        p = _write_jsonl(
            '{"type": "user"}\n'
            'this is not json at all\n'
            '@@@garbage@@@\n'
            '{"type": "assistant"}\n'
            '!@#$%^&*()\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            assert len(events) == 2
            assert diag.error_count >= 1
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_malformed_json_with_partial_structure(self):
        """JSON with missing braces must not crash.

        Note: the parser tracks brace depth across lines, so unbalanced
        opening braces cause subsequent lines to be accumulated.  When
        EOF is reached with depth > 0, the unterminated fragment is
        silently dropped.  The key invariant is: no uncaught exception.
        """
        p = _write_jsonl(
            '{"type": "user"\n'
            '{"type": "assistant", "message": {"role": "assistant"\n'
            '{"good": true}\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            # No crash -- that is the invariant we are testing.
            assert isinstance(events, list)
            assert isinstance(diag, JsonlDiagnostics)
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_non_dict_json_values(self):
        """Valid JSON that is not a dict (strings, numbers, arrays) must be
        silently skipped, not crash downstream."""
        p = _write_jsonl(
            '{"type": "user"}\n'
            '"bare string"\n'
            "42\n"
            "true\n"
            "null\n"
            "[1, 2, 3]\n"
            '{"type": "assistant"}\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            assert len(events) == 2
            assert diag.warning_count >= 1
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_unicode_garbage_in_jsonl(self):
        """Unicode garbage mixed with valid JSON must not crash."""
        p = _write_jsonl(
            '{"type": "user"}\n'
            '\x00\x01\x02binary garbage\xff\xfe\n'
            '{"type": "assistant"}\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            assert len(events) == 2
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_very_long_bad_line(self):
        """A very long unparseable line must not cause memory issues."""
        garbage = "x" * 100_000
        p = _write_jsonl(
            '{"type": "user"}\n'
            f'{garbage}\n'
            '{"type": "assistant"}\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            assert len(events) == 2
            assert diag.error_count >= 1
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_adapter_with_bad_json_does_not_crash(self):
        """Claude adapter must not raise uncaught exceptions on bad JSON."""
        from session_browser.sources import claude

        lines = [
            {"type": "user", "message": {"role": "user", "content": "hello"},
             "timestamp": "2026-05-02T00:00:00.000Z", "cwd": "/test",
             "entrypoint": "cli", "gitBranch": "main"},
            "totally not json",
            {"type": "assistant", "message": {"id": "msg-1", "model": "test",
             "role": "assistant", "content": [{"type": "text", "text": "hi"}],
             "usage": {"input_tokens": 10, "output_tokens": 5},
             "stop_reason": "end_turn"},
             "timestamp": "2026-05-02T00:00:01.000Z"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            original = claude.CLAUDE_DATA_DIR
            claude.CLAUDE_DATA_DIR = Path(tmpdir)
            try:
                project_dir = Path(tmpdir) / "projects" / "test-proj"
                project_dir.mkdir(parents=True)
                session_file = project_dir / "sid-bad.jsonl"
                session_file.write_text(
                    json.dumps(lines[0]) + "\n" + lines[1] + "\n" + json.dumps(lines[2]),
                    encoding="utf-8",
                )

                # Must not raise
                summary, messages, tool_calls, subagent_runs = (
                    claude.parse_session_detail("test-proj", "sid-bad")
                )
                assert isinstance(summary, SessionSummary)
            finally:
                claude.CLAUDE_DATA_DIR = original


# ─── 5. Empty file tolerance ─────────────────────────────────────────────


class TestEmptyFileTolerance:
    """Empty and near-empty files must not raise uncaught exceptions."""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_completely_empty_file(self):
        """A zero-byte file must return empty results, not crash."""
        p = _write_jsonl("")
        try:
            events, diag = parse_jsonl_events(p)
            assert events == []
            assert isinstance(diag, JsonlDiagnostics)
            assert diag.events_parsed == 0
            assert diag.error_count == 0
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_whitespace_only_file(self):
        """A file with only whitespace must return empty results."""
        p = _write_jsonl("\n\n  \t\n")
        try:
            events, diag = parse_jsonl_events(p)
            assert events == []
            assert diag.events_parsed == 0
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_adapter_with_missing_session_file(self):
        """Claude adapter must gracefully handle missing session file."""
        from session_browser.sources import claude

        with tempfile.TemporaryDirectory() as tmpdir:
            original = claude.CLAUDE_DATA_DIR
            claude.CLAUDE_DATA_DIR = Path(tmpdir)
            try:
                summary, messages, tool_calls, subagent_runs = (
                    claude.parse_session_detail("test-proj", "nonexistent-session")
                )
                assert isinstance(summary, SessionSummary)
                assert summary.agent == "claude_code"
                assert messages == []
                assert tool_calls == []
                assert subagent_runs == []
            finally:
                claude.CLAUDE_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_adapter_with_missing_session_file(self):
        """Codex adapter must gracefully handle missing session file."""
        from session_browser.sources import codex

        with tempfile.TemporaryDirectory() as tmpdir:
            original = codex.CODEX_DATA_DIR
            codex.CODEX_DATA_DIR = Path(tmpdir)
            try:
                summary, messages, tool_calls, subagent_runs = (
                    codex.parse_session_detail("nonexistent-session")
                )
                assert isinstance(summary, SessionSummary)
                assert summary.agent == "codex"
                assert messages == []
                assert tool_calls == []
                assert subagent_runs == []
            finally:
                codex.CODEX_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_qoder_adapter_with_missing_session_file(self):
        """Qoder adapter must gracefully handle missing session file."""
        from session_browser.sources import qoder

        with tempfile.TemporaryDirectory() as tmpdir:
            original = qoder.QODER_DATA_DIR
            qoder.QODER_DATA_DIR = Path(tmpdir)
            try:
                summary, messages, tool_calls, subagent_runs = (
                    qoder.parse_session_detail("test-proj", "nonexistent-session")
                )
                assert isinstance(summary, SessionSummary)
                assert summary.agent == "qoder"
                assert messages == []
                assert tool_calls == []
                assert subagent_runs == []
            finally:
                qoder.QODER_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_parse_history_with_no_data_dir(self):
        """parse_history must return empty list when data dir is empty."""
        from session_browser.sources import claude

        with tempfile.TemporaryDirectory() as tmpdir:
            original = claude.CLAUDE_DATA_DIR
            claude.CLAUDE_DATA_DIR = Path(tmpdir)
            try:
                result = claude.parse_history()
                assert result == []
            finally:
                claude.CLAUDE_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_parse_session_index_with_no_data_dir(self):
        """parse_session_index must return empty list when data dir is empty."""
        from session_browser.sources import codex

        with tempfile.TemporaryDirectory() as tmpdir:
            original = codex.CODEX_DATA_DIR
            codex.CODEX_DATA_DIR = Path(tmpdir)
            try:
                result = codex.parse_session_index()
                assert result == []
            finally:
                codex.CODEX_DATA_DIR = original

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_read_threads_db_with_no_data_dir(self):
        """read_threads_db must return empty dict when data dir is empty."""
        from session_browser.sources import codex

        with tempfile.TemporaryDirectory() as tmpdir:
            original = codex.CODEX_DATA_DIR
            codex.CODEX_DATA_DIR = Path(tmpdir)
            try:
                result = codex.read_threads_db()
                assert result == {}
            finally:
                codex.CODEX_DATA_DIR = original
