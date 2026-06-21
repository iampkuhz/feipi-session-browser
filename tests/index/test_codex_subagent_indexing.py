"""Codex subagent threads must not become top-level indexed sessions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

PARENT_ID = "parent-thread"
CHILD_ID = "child-thread"


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _rollout_events(session_id: str, *, parent_id: str = "") -> list[dict]:
    is_child = bool(parent_id)
    source: object = "vscode"
    extra_meta = {"thread_source": "user"}
    if is_child:
        source = {
            "subagent": {
                "thread_spawn": {
                    "parent_thread_id": parent_id,
                    "depth": 1,
                    "agent_role": "implementer",
                    "agent_nickname": "Child",
                    "agent_path": None,
                }
            }
        }
        extra_meta = {
            "thread_source": "subagent",
            "parent_thread_id": parent_id,
            "agent_role": "implementer",
            "agent_nickname": "Child",
        }

    events = [
        {
            "timestamp": "2026-06-19T00:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": "/repo/codex-fixture",
                "source": source,
                "model_provider": "openai",
                **extra_meta,
            },
        },
        {
            "timestamp": "2026-06-19T00:00:01.000Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": f"run {session_id}"},
        },
    ]
    if not is_child:
        events.extend(
            [
                {
                    "timestamp": "2026-06-19T00:00:02.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "call_id": "call_spawn",
                        "name": "spawn_agent",
                        "arguments": json.dumps({"agent_type": "implementer", "message": "work"}),
                    },
                },
                {
                    "timestamp": "2026-06-19T00:00:03.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call_spawn",
                        "output": json.dumps({"agent_id": CHILD_ID, "nickname": "Child"}),
                    },
                },
            ]
        )
    events.extend(
        [
            {
                "timestamp": "2026-06-19T00:00:04.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 20,
                            "output_tokens": 10,
                            "total_tokens": 110,
                        }
                    },
                },
            },
            {
                "timestamp": "2026-06-19T00:00:05.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": f"done {session_id}"}],
                },
            },
        ]
    )
    return events


def _setup_codex_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    data_dir = tmp_path / "codex_data"
    rollout_dir = data_dir / "sessions" / "2026" / "06" / "19"
    parent_path = rollout_dir / f"rollout-2026-06-19T00-00-00-{PARENT_ID}.jsonl"
    child_path = rollout_dir / f"rollout-2026-06-19T00-00-01-{CHILD_ID}.jsonl"
    _write_jsonl(parent_path, _rollout_events(PARENT_ID))
    _write_jsonl(child_path, _rollout_events(CHILD_ID, parent_id=PARENT_ID))

    conn = sqlite3.connect(data_dir / "state_5.sqlite")
    conn.execute(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            title TEXT,
            cwd TEXT,
            model TEXT,
            tokens_used INTEGER,
            created_at INTEGER,
            updated_at INTEGER,
            git_branch TEXT,
            source TEXT,
            model_provider TEXT,
            cli_version TEXT,
            rollout_path TEXT,
            first_user_message TEXT,
            thread_source TEXT,
            agent_role TEXT,
            agent_nickname TEXT,
            agent_path TEXT
        )
        """
    )
    rows = [
        (
            PARENT_ID,
            "Parent session",
            "/repo/codex-fixture",
            "gpt-test",
            110,
            1,
            5,
            "main",
            "vscode",
            "openai",
            "test",
            str(parent_path),
            "parent prompt",
            "user",
            "",
            "",
            "",
        ),
        (
            CHILD_ID,
            "Child subagent",
            "/repo/codex-fixture",
            "gpt-test",
            110,
            2,
            4,
            "main",
            json.dumps(
                {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": PARENT_ID,
                            "depth": 1,
                            "agent_role": "implementer",
                        }
                    }
                }
            ),
            "openai",
            "test",
            str(child_path),
            "child prompt",
            "subagent",
            "implementer",
            "Child",
            "",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO threads (
            id, title, cwd, model, tokens_used, created_at, updated_at,
            git_branch, source, model_provider, cli_version, rollout_path,
            first_user_message, thread_source, agent_role, agent_nickname, agent_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()

    from session_browser import config
    from session_browser.sources import codex_session_source as codex_source

    monkeypatch.setattr(config, "CODEX_DATA_DIR", data_dir)
    monkeypatch.setattr(codex_source, "CODEX_DATA_DIR", data_dir)
    return data_dir, child_path


def _remove_child_thread_db_row(data_dir: Path) -> None:
    conn = sqlite3.connect(data_dir / "state_5.sqlite")
    try:
        conn.execute("DELETE FROM threads WHERE id = ?", (CHILD_ID,))
        conn.commit()
    finally:
        conn.close()


def _write_child_session_index(data_dir: Path) -> None:
    (data_dir / "session_index.jsonl").write_text(
        json.dumps(
            {
                "id": CHILD_ID,
                "thread_name": "Child subagent",
                "updated_at": "2026-06-19T00:00:05.000Z",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.contract_case("DATA-INDEX-001")
def test_full_scan_excludes_codex_subagent_threads(tmp_path, monkeypatch):
    """Full scan indexes the parent session, not the spawned child thread."""
    _setup_codex_fixture(tmp_path, monkeypatch)

    from session_browser.index.indexer import full_scan

    db_path = tmp_path / "index.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    result = full_scan(conn, verbose=False, agent="codex")

    rows = conn.execute(
        "SELECT session_key, subagent_instance_count FROM sessions ORDER BY session_key"
    ).fetchall()
    conn.close()

    assert result["codex_count"] == 1
    assert [row["session_key"] for row in rows] == [f"codex:{PARENT_ID}"]
    assert rows[0]["subagent_instance_count"] == 1


@pytest.mark.contract_case("DATA-INDEX-001")
def test_full_scan_excludes_fallback_codex_subagent_threads(tmp_path, monkeypatch):
    """Fallback session_index entries are peeked and skipped when they are children."""
    data_dir, _child_path = _setup_codex_fixture(tmp_path, monkeypatch)
    _remove_child_thread_db_row(data_dir)
    _write_child_session_index(data_dir)

    from session_browser.index.indexer import full_scan

    db_path = tmp_path / "index.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    result = full_scan(conn, verbose=False, agent="codex")

    rows = conn.execute(
        "SELECT session_key, subagent_instance_count FROM sessions ORDER BY session_key"
    ).fetchall()
    conn.close()

    assert result["codex_count"] == 1
    assert [row["session_key"] for row in rows] == [f"codex:{PARENT_ID}"]
    assert rows[0]["subagent_instance_count"] == 1


@pytest.mark.contract_case("DATA-INDEX-001")
def test_incremental_scan_prunes_stale_codex_subagent_row(tmp_path, monkeypatch):
    """Incremental scan removes a child row left by older indexer logic."""
    _setup_codex_fixture(tmp_path, monkeypatch)

    from session_browser.domain.models import SessionSummary
    from session_browser.index.indexer import full_scan, incremental_scan
    from session_browser.index.writers import upsert_session, upsert_session_artifact

    db_path = tmp_path / "index.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    full_scan(conn, verbose=False, agent="codex")

    stale = SessionSummary(
        agent="codex",
        session_id=CHILD_ID,
        title="Stale child",
        project_key="/repo/codex-fixture",
        project_name="codex-fixture",
        cwd="/repo/codex-fixture",
        started_at="2026-06-19T00:00:00+00:00",
        ended_at="2026-06-19T00:00:05+00:00",
        model="gpt-test",
    )
    upsert_session(conn, stale, file_mtime=1, file_path="/tmp/stale-child.jsonl")
    upsert_session_artifact(
        conn,
        session_key=f"codex:{CHILD_ID}",
        artifact_type="normalized",
        path="/tmp/stale-child.normalized.json",
    )
    conn.commit()

    result = incremental_scan(conn, verbose=False, agent="codex")

    session_keys = [
        row["session_key"]
        for row in conn.execute("SELECT session_key FROM sessions ORDER BY session_key")
    ]
    artifact = conn.execute(
        "SELECT * FROM session_artifacts WHERE session_key = ?",
        (f"codex:{CHILD_ID}",),
    ).fetchone()
    conn.close()

    assert result["pruned_subagents"] == 1
    assert session_keys == [f"codex:{PARENT_ID}"]
    assert artifact is None


def test_codex_subagent_child_index_scans_day_directory_once(tmp_path, monkeypatch):
    """Multiple parent lookups in one day directory reuse the child index."""
    from session_browser.sources import codex_session_source as codex_source

    day_dir = tmp_path / "codex_data" / "sessions" / "2026" / "06" / "19"
    parent_1 = day_dir / "rollout-2026-06-19T00-00-00-parent-1.jsonl"
    child_1 = day_dir / "rollout-2026-06-19T00-00-01-child-1.jsonl"
    parent_2 = day_dir / "rollout-2026-06-19T00-00-02-parent-2.jsonl"
    child_2 = day_dir / "rollout-2026-06-19T00-00-03-child-2.jsonl"
    unrelated_child = day_dir / "rollout-2026-06-19T00-00-04-child-3.jsonl"

    _write_jsonl(parent_1, _rollout_events("parent-1"))
    _write_jsonl(child_1, _rollout_events("child-1", parent_id="parent-1"))
    _write_jsonl(parent_2, _rollout_events("parent-2"))
    _write_jsonl(child_2, _rollout_events("child-2", parent_id="parent-2"))
    _write_jsonl(unrelated_child, _rollout_events("child-3", parent_id="other-parent"))

    original_peek = codex_source.peek_codex_session_meta
    peeked: list[Path] = []

    def counted_peek(path):
        peeked.append(Path(path))
        return original_peek(path)

    monkeypatch.setattr(codex_source, "peek_codex_session_meta", counted_peek)
    codex_source.clear_codex_subagent_index_cache()

    assert codex_source.get_codex_subagent_child_paths(parent_1, "parent-1") == [child_1]
    assert codex_source.get_codex_subagent_child_paths(parent_2, "parent-2") == [child_2]
    assert codex_source.get_codex_subagent_child_paths(parent_1, "parent-1") == [child_1]

    assert len(peeked) == len(list(day_dir.glob("rollout-*.jsonl")))
