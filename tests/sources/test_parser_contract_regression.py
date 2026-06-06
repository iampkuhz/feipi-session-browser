"""parser 合同回归测试。

验证三个 adapter 模块（claude、codex、qoder）暴露可调用的公共函数签名、
正确处理各自的 fixture 语料库、返回类型匹配约定，
并能优雅容错坏 JSON 和空文件，不会抛出未捕获异常。

覆盖：
1. 公共函数签名可导入且可调用。
2. 每个 adapter 能处理其 fixture 语料库的 JSONL 类型。
3. 返回值类型与约定匹配（events: list[dict]、
   diagnostics: JsonlDiagnostics、summary: SessionSummary）。
4. 坏 JSON 行不会导致未捕获异常。
5. 空 JSONL 文件不会导致未捕获异常。
"""

from __future__ import annotations

import pytest
import inspect
import json
import tempfile
from pathlib import Path
from typing import Callable

# ─── 共享类型 ────────────────────────────────────────────────────────────

from session_browser.domain.models import SessionSummary, ChatMessage, ToolCall
from session_browser.sources.jsonl_reader import (
    JsonlDiagnostics,
    parse_jsonl_events,
)

# ─── fixture 辅助函数 ─────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "sources"


def _write_jsonl(content: str) -> Path:
    """将 *content* 写入临时 .jsonl 文件并返回其 Path。"""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with open(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return Path(path)


# ─── 1. 公共函数签名可调用 ────────────────────────────────────────────────


class TestPublicSignatures:
    """验证每个 adapter 的公共 API 可导入且可调用。"""

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


# ─── 2. Adapter fixture 语料库合同 ─────────────────────────────────────


class TestFixtureCorpusContract:
    """每个 adapter 必须无误处理其 fixture 语料库。"""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_fixture_parses(self):
        """Claude 风格的 JSONL fixture 必须解析为事件 + 诊断信息。"""
        jsonl_path = FIXTURES_DIR / "claude_valid.jsonl"
        assert jsonl_path.exists(), f"Fixture not found: {jsonl_path}"
        events, diag = parse_jsonl_events(jsonl_path)
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(ev, dict) for ev in events)
        assert isinstance(diag, JsonlDiagnostics)
        assert diag.events_parsed == len(events)

        # Claude fixture 包含 user 和 assistant 类型
        types = {ev.get("type") for ev in events}
        assert "user" in types
        assert "assistant" in types

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_codex_fixture_parses(self):
        """Codex 风格的 JSONL fixture 必须解析为事件 + 诊断信息。"""
        jsonl_path = FIXTURES_DIR / "codex_valid.jsonl"
        assert jsonl_path.exists(), f"Fixture not found: {jsonl_path}"
        events, diag = parse_jsonl_events(jsonl_path)
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(ev, dict) for ev in events)
        assert isinstance(diag, JsonlDiagnostics)
        assert diag.events_parsed == len(events)

        # Codex fixture 包含 message、tool_call、tool_result 类型
        types = {ev.get("type") for ev in events}
        assert "message" in types
        assert "tool_call" in types
        assert "tool_result" in types

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_qoder_fixture_parses(self):
        """Qoder 风格的 JSONL fixture 必须解析为事件 + 诊断信息。"""
        jsonl_path = FIXTURES_DIR / "qoder_valid.jsonl"
        assert jsonl_path.exists(), f"Fixture not found: {jsonl_path}"
        events, diag = parse_jsonl_events(jsonl_path)
        assert isinstance(events, list)
        assert len(events) > 0
        assert all(isinstance(ev, dict) for ev in events)
        assert isinstance(diag, JsonlDiagnostics)
        assert diag.events_parsed == len(events)

        # Qoder fixture 包含 user 和 assistant 类型（类似 Claude 格式）
        types = {ev.get("type") for ev in events}
        assert "user" in types
        assert "assistant" in types


# ─── 3. 返回值类型契约 ─────────────────────────────────────────────


class TestReturnValueContracts:
    """验证返回值类型和结构与预期契约匹配。"""

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
            # 必填数值字段
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


# ─── 4. 坏 JSON 容错 ───────────────────────────────────────────────


class TestBadJsonTolerance:
    """坏 JSON 不得引发未捕获异常。"""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_completely_unparseable_lines(self):
        """完全不是 JSON 的行必须被静默跳过。"""
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
        """缺少大括号的畸形 JSON 不得导致崩溃。

        注意：解析器会跨行追踪花括号深度，因此不平衡的
        开大括号会导致后续行被累积。当到达 EOF 且深度 > 0
        时，未终止的片段会被静默丢弃。关键不变量是：不抛出
        未捕获异常。
        """
        p = _write_jsonl(
            '{"type": "user"\n'
            '{"type": "assistant", "message": {"role": "assistant"\n'
            '{"good": true}\n'
        )
        try:
            events, diag = parse_jsonl_events(p)
            # 不崩溃 —— 这是我们要测试的不变量。
            assert isinstance(events, list)
            assert isinstance(diag, JsonlDiagnostics)
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_non_dict_json_values(self):
        """有效的 JSON 但不是字典（字符串、数字、数组）必须被
        静默跳过，不得向下游崩溃。"""
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
        """Unicode 乱码与有效 JSON 混合不得导致崩溃。"""
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
        """非常长的不可解析行不得导致内存问题。"""
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
        """Claude adapter 在处理坏 JSON 时不得抛出未捕获异常。"""
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


# ─── 5. 空文件容错 ─────────────────────────────────────────────


class TestEmptyFileTolerance:
    """空文件和近空文件不得引发未捕获异常。"""

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_completely_empty_file(self):
        """零字节文件必须返回空结果，不崩溃。"""
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
        """仅包含空白字符的文件必须返回空结果。"""
        p = _write_jsonl("\n\n  \t\n")
        try:
            events, diag = parse_jsonl_events(p)
            assert events == []
            assert diag.events_parsed == 0
        finally:
            p.unlink(missing_ok=True)

    @pytest.mark.contract_case("DATA-SOURCE-001")
    def test_claude_adapter_with_missing_session_file(self):
        """Claude adapter 必须优雅处理缺失的会话文件。"""
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
        """Codex adapter 必须优雅处理缺失的会话文件。"""
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
        """Qoder adapter 必须优雅处理缺失的会话文件。"""
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
        """当数据目录为空时，parse_history 必须返回空列表。"""
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
        """当数据目录为空时，parse_session_index 必须返回空列表。"""
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
        """当数据目录为空时，read_threads_db 必须返回空字典。"""
        from session_browser.sources import codex

        with tempfile.TemporaryDirectory() as tmpdir:
            original = codex.CODEX_DATA_DIR
            codex.CODEX_DATA_DIR = Path(tmpdir)
            try:
                result = codex.read_threads_db()
                assert result == {}
            finally:
                codex.CODEX_DATA_DIR = original
