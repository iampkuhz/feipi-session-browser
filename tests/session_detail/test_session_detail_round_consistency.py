"""T020: Qoder session detail rounds consistency gate.

Validates that Qoder cache sessions with assistant_message_count > 0 in the
index return a matching number of rounds from the detail route/parser.
Indexed sessions must NOT degrade to rounds=0 due to file-not-found.

Covers:
a. Qoder project (CLI) session: parse + build_rounds returns rounds > 0.
b. Qoder cache (GUI) session: parse + build_rounds returns rounds > 0
   matching the indexed assistant_message_count.
c. File-not-found scenario: when a session is indexed but the source file
   is missing, detail should NOT silently return 0 rounds — it must either
   return matching rounds or carry a diagnostic flag.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────

def _make_qoder_project_fixture(tmpdir: str, session_id: str, jsonl_content: str) -> str:
    """Create a Qoder project/ layout with a JSONL session file.

    Returns the CLAUDE_DATA_DIR path.
    Layout:
      {tmpdir}/projects/my-test-proj/{session_id}.jsonl
    """
    projects_dir = os.path.join(tmpdir, "projects", "my-test-proj")
    os.makedirs(projects_dir)
    jsonl_path = os.path.join(projects_dir, f"{session_id}.jsonl")
    with open(jsonl_path, "w") as f:
        f.write(jsonl_content)
    return tmpdir


def _make_qoder_cache_fixture(tmpdir: str, session_id: str, jsonl_content: str) -> str:
    """Create a Qoder cache/projects/ layout with a JSONL session file.

    Returns the QODER_DATA_DIR path.
    Layout:
      {tmpdir}/cache/projects/my-test-proj/conversation-history/{session_id}/{session_id}.jsonl
    """
    cache_dir = os.path.join(
        tmpdir, "cache", "projects", "my-test-proj",
        "conversation-history", session_id,
    )
    os.makedirs(cache_dir)
    jsonl_path = os.path.join(cache_dir, f"{session_id}.jsonl")
    with open(jsonl_path, "w") as f:
        f.write(jsonl_content)
    return tmpdir


# 3-round Qoder project (CLI) session with real usage data (2 user messages, 3 assistant responses)
QODER_3ROUND_JSONL = """\
{"type": "user", "message": {"role": "user", "content": "请帮我写一个 Hello World"}, "timestamp": "2026-05-02T14:00:00.000Z", "cwd": "/Users/test/proj", "entrypoint": "cli", "gitBranch": "main", "sessionId": "qoder-session-001", "version": "1.0.0"}
{"type": "assistant", "message": {"model": "qwen3.6-plus", "role": "assistant", "content": [{"type": "text", "text": "好的，我来帮你写。"}], "usage": {"input_tokens": 100, "output_tokens": 20}}, "timestamp": "2026-05-02T14:00:05.000Z", "sessionId": "qoder-session-001", "version": "1.0.0"}
{"type": "user", "message": {"role": "user", "content": "再加一个测试文件"}, "timestamp": "2026-05-02T14:01:00.000Z", "sessionId": "qoder-session-001", "version": "1.0.0"}
{"type": "assistant", "message": {"model": "qwen3.6-plus", "role": "assistant", "content": [{"type": "text", "text": "测试文件已创建。"}], "usage": {"input_tokens": 200, "output_tokens": 30}}, "timestamp": "2026-05-02T14:01:05.000Z", "sessionId": "qoder-session-001", "version": "1.0.0"}
{"type": "assistant", "message": {"model": "qwen3.6-plus", "role": "assistant", "content": [{"type": "text", "text": "完成！"}], "usage": {"input_tokens": 50, "output_tokens": 10}}, "timestamp": "2026-05-02T14:01:10.000Z", "sessionId": "qoder-session-001", "version": "1.0.0"}
"""

# Qoder cache (GUI) session format — uses "role" at top level, no timestamps
QODER_CACHE_3ROUND_JSONL = """\
{"role": "user", "message": {"content": "请帮我写一个 Hello World"}}
{"role": "assistant", "message": {"content": [{"type": "text", "text": "好的，我来帮你写。"}]}}
{"role": "user", "message": {"content": "再加一个测试文件"}}
{"role": "assistant", "message": {"content": [{"type": "text", "text": "测试文件已创建。"}]}}
{"role": "assistant", "message": {"content": [{"type": "text", "text": "完成！"}]}}
"""

SESSION_ID = "qoder-session-001"
PROJECT_KEY = "my-test-proj"


def _index_session_from_data_dir(data_dir: str, sqlite_path: str) -> tuple:
    """Index sessions from a CLAUDE_DATA_DIR layout into SQLite.

    Returns (session_key, indexed_row_dict) for the target session.
    """
    import sys
    import importlib

    SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))

    old_data_dir = os.environ.get("QODER_DATA_DIR", "")
    os.environ["QODER_DATA_DIR"] = data_dir

    # Reload config + dependent modules so they pick up the new env var
    if "session_browser.config" in sys.modules:
        importlib.reload(sys.modules["session_browser.config"])
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]

    try:
        from session_browser.index.indexer import init_schema, upsert_session
        from session_browser.sources.qoder import scan_all_sessions

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        init_schema(conn)

        for summary in scan_all_sessions():
            upsert_session(conn, summary)

        conn.commit()
        session_key = f"qoder:{SESSION_ID}"
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_key = ?",
            (session_key,),
        ).fetchone()
        conn.close()

        if row is None:
            return None, None
        return session_key, dict(row)
    finally:
        if old_data_dir:
            os.environ["QODER_DATA_DIR"] = old_data_dir
        else:
            os.environ.pop("QODER_DATA_DIR", None)


def _parse_and_build_rounds(data_dir: str, session_id: str, project_key: str) -> tuple:
    """Parse session detail and build rounds.

    Returns (summary, messages, rounds_count).
    """
    import sys
    import importlib

    SB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(SB_ROOT, "src"))

    old_data_dir = os.environ.get("QODER_DATA_DIR", "")
    os.environ["QODER_DATA_DIR"] = data_dir

    if "session_browser.config" in sys.modules:
        importlib.reload(sys.modules["session_browser.config"])
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]

    try:
        from session_browser.sources.qoder import parse_session_detail
        from session_browser.web.presenters.session_detail import build_rounds

        summary, messages, tool_calls, subagent_runs = parse_session_detail(
            project_key, session_id, verbose=False
        )

        rounds = build_rounds(
            messages, tool_calls,
            session.input_tokens if (session := summary) else 0,
            session.output_tokens,
            session.cached_input_tokens,
            session.cached_output_tokens,
            "qoder",
            md_filter=lambda s: s,
        )
        return summary, messages, len(rounds)
    finally:
        if old_data_dir:
            os.environ["QODER_DATA_DIR"] = old_data_dir
        else:
            os.environ.pop("QODER_DATA_DIR", None)


# ─── Tests ────────────────────────────────────────────────────────────────


class TestQoderProjectSessionRoundConsistency:
    """Qoder project (CLI) sessions: detail rounds must match indexed counts."""

    def test_index_has_assistant_message_count(self):
        """After indexing a Qoder project session, assistant_message_count > 0."""
        tmpdir = tempfile.mkdtemp(prefix="qoder_project_round_")
        try:
            _make_qoder_project_fixture(tmpdir, SESSION_ID, QODER_3ROUND_JSONL)
            data_dir = tmpdir  # QODER_DATA_DIR points here
            sqlite_path = os.path.join(tmpdir, "index.sqlite")

            session_key, row = _index_session_from_data_dir(data_dir, sqlite_path)
            assert session_key is not None, "Session was not indexed"
            assert row["assistant_message_count"] == 3, (
                f"Expected assistant_message_count=3, got {row['assistant_message_count']}"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_detail_rounds_match_indexed_count(self):
        """Detail rounds must equal indexed assistant_message_count."""
        tmpdir = tempfile.mkdtemp(prefix="qoder_project_round_")
        try:
            _make_qoder_project_fixture(tmpdir, SESSION_ID, QODER_3ROUND_JSONL)
            data_dir = tmpdir

            # Index
            sqlite_path = os.path.join(tmpdir, "index.sqlite")
            session_key, row = _index_session_from_data_dir(data_dir, sqlite_path)
            assert row is not None
            indexed_rounds = row["assistant_message_count"]

            # Detail
            summary, messages, detail_rounds = _parse_and_build_rounds(
                data_dir, SESSION_ID, PROJECT_KEY
            )

            assert detail_rounds > 0, (
                f"Detail returned 0 rounds but index has {indexed_rounds}. "
                f"This is the SD-14 bug: indexed session degraded to rounds=0."
            )
            assert detail_rounds == indexed_rounds, (
                f"Detail rounds ({detail_rounds}) != indexed rounds ({indexed_rounds})"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_detail_rounds_not_zero_when_assistant_count_positive(self):
        """If assistant_message_count > 0 in index, detail must NOT return 0 rounds."""
        tmpdir = tempfile.mkdtemp(prefix="qoder_project_round_")
        try:
            _make_qoder_project_fixture(tmpdir, SESSION_ID, QODER_3ROUND_JSONL)
            data_dir = tmpdir
            sqlite_path = os.path.join(tmpdir, "index.sqlite")

            _, row = _index_session_from_data_dir(data_dir, sqlite_path)
            assert row["assistant_message_count"] > 0

            summary, messages, detail_rounds = _parse_and_build_rounds(
                data_dir, SESSION_ID, PROJECT_KEY
            )

            assert detail_rounds > 0, (
                f"assistant_message_count={row['assistant_message_count']} but detail rounds=0"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestQoderCacheSessionRoundConsistency:
    """Qoder cache (GUI) sessions: detail rounds must match indexed counts."""

    def test_cache_session_indexed_with_positive_count(self):
        """Cache sessions must be indexed with assistant_message_count > 0."""
        tmpdir = tempfile.mkdtemp(prefix="qoder_cache_round_")
        try:
            _make_qoder_cache_fixture(tmpdir, SESSION_ID, QODER_CACHE_3ROUND_JSONL)
            data_dir = tmpdir
            sqlite_path = os.path.join(tmpdir, "index.sqlite")

            session_key, row = _index_session_from_data_dir(data_dir, sqlite_path)
            assert session_key is not None, "Cache session was not indexed"
            assert row["assistant_message_count"] == 3, (
                f"Expected assistant_message_count=3, got {row['assistant_message_count']}"
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_cache_session_detail_rounds_match_index(self):
        """Cache session detail must return rounds matching the index.

        NOTE: This test documents the SD-14 gap. Currently
        parse_session_detail only searches projects/ (CLI) via
        _find_session_file and does NOT search cache/projects/ (GUI).
        So cache sessions get indexed with assistant_message_count > 0
        but detail returns 0 rounds (FILE_NOT_FOUND).

        After the fix, this assertion should pass (detail_rounds > 0).
        """
        tmpdir = tempfile.mkdtemp(prefix="qoder_cache_round_")
        try:
            _make_qoder_cache_fixture(tmpdir, SESSION_ID, QODER_CACHE_3ROUND_JSONL)
            data_dir = tmpdir
            sqlite_path = os.path.join(tmpdir, "index.sqlite")

            _, row = _index_session_from_data_dir(data_dir, sqlite_path)
            assert row is not None
            indexed_rounds = row["assistant_message_count"]
            assert indexed_rounds > 0, "Cache session must be indexed with positive count"

            # Cache sessions use project_key from the fixture
            cache_project_key = "my-test-proj"
            summary, messages, detail_rounds = _parse_and_build_rounds(
                data_dir, SESSION_ID, cache_project_key
            )

            # SD-14 gate: detail rounds must NOT be 0 when index has > 0
            # Currently fails because _find_session_file does not search cache/
            assert detail_rounds > 0, (
                f"Cache session detail returned 0 rounds but index has {indexed_rounds}. "
                f"Root cause: parse_session_detail._find_session_file only searches "
                f"projects/, not cache/projects/. Fix: add cache lookup path."
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestQoderFileNotFoundRoundConsistency:
    """File-not-found scenario: indexed session with missing source file."""

    def test_index_without_source_file_returns_zero_rounds_with_diagnostic(self):
        """When a session is indexed but the source file is missing,
        parse_session_detail returns 0 rounds but MUST attach parse_diagnostics."""
        tmpdir = tempfile.mkdtemp(prefix="qoder_notfound_round_")
        try:
            # Index with fixture data first
            _make_qoder_project_fixture(tmpdir, SESSION_ID, QODER_3ROUND_JSONL)
            data_dir = tmpdir
            sqlite_path = os.path.join(tmpdir, "index.sqlite")

            _, row = _index_session_from_data_dir(data_dir, sqlite_path)
            assert row is not None
            indexed_rounds = row["assistant_message_count"]
            assert indexed_rounds > 0

            # Now remove the source file to simulate "file not found"
            projects_dir = os.path.join(tmpdir, "projects", "my-test-proj")
            jsonl_path = os.path.join(projects_dir, f"{SESSION_ID}.jsonl")
            if os.path.exists(jsonl_path):
                os.remove(jsonl_path)

            # Parse detail again — file is gone
            summary, messages, detail_rounds = _parse_and_build_rounds(
                data_dir, SESSION_ID, PROJECT_KEY
            )

            # detail_rounds will be 0 (expected for missing file)
            # BUT the summary MUST have parse_diagnostics to explain why
            if detail_rounds == 0:
                diag = getattr(summary, "parse_diagnostics", None)
                assert diag is not None, (
                    "When detail rounds=0 due to file-not-found, "
                    "summary MUST carry parse_diagnostics to explain the discrepancy."
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestDbCanonicalMergeStrategy:
    """SD-14: DB summary is canonical. raw parse must NOT overwrite confirmed fields.

    The session detail endpoint merges raw_summary (fresh parse) with the
    DB session (indexed canonical data). The merge strategy must be:
    - DB fields that are non-zero are authoritative -- do NOT overwrite.
    - raw_summary only supplements fields that are empty/null/zero in DB.
    - assistant_message_count (round count) must stay consistent between
      list page and detail page.
    """

    def test_db_canonical_assistant_count_not_overwritten_by_zero(self):
        """If DB has assistant_message_count=3, raw_summary=0 must NOT overwrite it."""
        from session_browser.domain.models import SessionSummary
        from session_browser.web.routes import _merge_raw_into_db_summary

        db_summary = SessionSummary(
            agent="qoder",
            session_id="test-session-001",
            title="Test Session",
            project_key="test-project",
            project_name="Test Project",
            cwd="/tmp/test",
            started_at="2026-05-02T14:00:00Z",
            ended_at="2026-05-02T14:05:00Z",
            duration_seconds=300.0,
            model_execution_seconds=250.0,
            tool_execution_seconds=50.0,
            model="qwen3.6-plus",
            git_branch="main",
            source="",
            user_message_count=2,
            assistant_message_count=3,
            tool_call_count=1,
            input_tokens=350,
            output_tokens=60,
            cached_input_tokens=0,
            cached_output_tokens=0,
            failed_tool_count=0,
            file_path="/tmp/test.jsonl",
        )

        raw_summary = SessionSummary(
            agent="qoder",
            session_id="test-session-001",
            title="",
            project_key="",
            project_name="",
            cwd="",
            started_at="",
            ended_at="",
            duration_seconds=0,
            model_execution_seconds=0,
            tool_execution_seconds=0,
            model="",
            git_branch="",
            source="",
            user_message_count=0,
            assistant_message_count=0,
            tool_call_count=0,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            cached_output_tokens=0,
            failed_tool_count=0,
            file_path="",
        )

        result = _merge_raw_into_db_summary(db_summary, raw_summary)

        assert result.assistant_message_count == 3, (
            f"DB canonical assistant_message_count=3 must NOT be overwritten by raw=0. "
            f"Got {result.assistant_message_count}. This is the SD-14 bug."
        )
        assert result.user_message_count == 2, "DB user_message_count must be preserved"
        assert result.tool_call_count == 1, "DB tool_call_count must be preserved"
        assert result.input_tokens == 350, "DB input_tokens must be preserved"
        assert result.output_tokens == 60, "DB output_tokens must be preserved"

    def test_raw_supplements_empty_db_fields(self):
        """raw_summary must fill in DB fields that are zero/empty."""
        from session_browser.domain.models import SessionSummary
        from session_browser.web.routes import _merge_raw_into_db_summary

        db_summary = SessionSummary(
            agent="qoder",
            session_id="test-session-002",
            title="",
            project_key="",
            project_name="",
            cwd="",
            started_at="",
            ended_at="2026-05-02T14:05:00Z",
            duration_seconds=0,
            model_execution_seconds=0,
            tool_execution_seconds=0,
            model="",
            git_branch="",
            source="",
            user_message_count=0,
            assistant_message_count=0,
            tool_call_count=0,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            cached_output_tokens=0,
            failed_tool_count=0,
            file_path="",
        )

        raw_summary = SessionSummary(
            agent="qoder",
            session_id="test-session-002",
            title="Parsed Title",
            project_key="parsed-project",
            project_name="Parsed Project",
            cwd="/tmp/parsed",
            started_at="2026-05-02T14:00:00Z",
            ended_at="2026-05-02T14:05:00Z",
            duration_seconds=300.0,
            model_execution_seconds=250.0,
            tool_execution_seconds=50.0,
            model="qwen3.6-plus",
            git_branch="main",
            source="",
            user_message_count=2,
            assistant_message_count=3,
            tool_call_count=1,
            input_tokens=350,
            output_tokens=60,
            cached_input_tokens=100,
            cached_output_tokens=20,
            failed_tool_count=0,
            file_path="/tmp/parsed.jsonl",
        )

        result = _merge_raw_into_db_summary(db_summary, raw_summary)

        assert result.assistant_message_count == 3
        assert result.user_message_count == 2
        assert result.tool_call_count == 1
        assert result.input_tokens == 350
        assert result.output_tokens == 60
        assert result.cached_input_tokens == 100
        assert result.cached_output_tokens == 20
        assert result.duration_seconds == 300.0

    def test_raw_none_returns_db_unchanged(self):
        """When raw_summary is None, DB summary must be returned as-is."""
        from session_browser.domain.models import SessionSummary
        from session_browser.web.routes import _merge_raw_into_db_summary

        db_summary = SessionSummary(
            agent="claude_code",
            session_id="claude-session-001",
            title="Claude Session",
            project_key="claude-project",
            project_name="Claude Project",
            cwd="/tmp/claude",
            started_at="2026-05-02T14:00:00Z",
            ended_at="2026-05-02T14:05:00Z",
            duration_seconds=300.0,
            model_execution_seconds=250.0,
            tool_execution_seconds=50.0,
            model="claude-sonnet-4-20250514",
            git_branch="main",
            source="",
            user_message_count=5,
            assistant_message_count=8,
            tool_call_count=10,
            input_tokens=1000,
            output_tokens=500,
            cached_input_tokens=200,
            cached_output_tokens=100,
            failed_tool_count=1,
            file_path="/tmp/claude.jsonl",
        )

        result = _merge_raw_into_db_summary(db_summary, None)

        assert result is db_summary, "DB summary must be returned unchanged when raw is None"

    def test_raw_duration_used_when_db_duration_is_zero(self):
        """duration_seconds should use raw value when DB has zero."""
        from session_browser.domain.models import SessionSummary
        from session_browser.web.routes import _merge_raw_into_db_summary

        db_summary = SessionSummary(
            agent="codex",
            session_id="codex-session-001",
            title="",
            project_key="",
            project_name="",
            cwd="",
            started_at="",
            ended_at="2026-05-02T14:05:00Z",
            duration_seconds=0,
            model_execution_seconds=0,
            tool_execution_seconds=0,
            model="",
            git_branch="",
            source="",
            user_message_count=0,
            assistant_message_count=0,
            tool_call_count=0,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            cached_output_tokens=0,
            failed_tool_count=0,
            file_path="",
        )

        raw_summary = SessionSummary(
            agent="codex",
            session_id="codex-session-001",
            title="",
            project_key="",
            project_name="",
            cwd="",
            started_at="",
            ended_at="2026-05-02T14:05:00Z",
            duration_seconds=450.0,
            model_execution_seconds=400.0,
            tool_execution_seconds=50.0,
            model="",
            git_branch="",
            source="",
            user_message_count=0,
            assistant_message_count=0,
            tool_call_count=0,
            input_tokens=0,
            output_tokens=0,
            cached_input_tokens=0,
            cached_output_tokens=0,
            failed_tool_count=0,
            file_path="",
        )

        result = _merge_raw_into_db_summary(db_summary, raw_summary)

        assert result.duration_seconds == 450.0, (
            "raw duration should be used when DB duration is zero"
        )
