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
