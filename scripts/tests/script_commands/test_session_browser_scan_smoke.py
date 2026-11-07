"""Scan script entry smoke test with isolated tmp fixtures.

This test ensures that `./scripts/session-browser.sh scan --full` works
end-to-end through the real script entry, launcher, env vars, SQLite index,
and scan-engine production path — without scanning real user data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'session-browser.sh'


# ─── Fixture creation helpers ──────────────────────────────────────


def _create_claude_fixture(data_dir: Path) -> None:
    """Create minimal Claude fixture: 1 history.jsonl entry + 1 transcript JSONL."""
    projects_dir = data_dir / 'projects'
    project_dir = projects_dir / '-test-project'
    project_dir.mkdir(parents=True, exist_ok=True)

    # history.jsonl — single session entry
    history_entry = {
        'sessionId': 'smoke-test-session-001',
        'cwd': '/test/project',
        'ts': '2024-01-01T00:00:00.000Z',
    }
    (data_dir / 'history.jsonl').write_text(json.dumps(history_entry) + '\n', encoding='utf-8')

    # Transcript JSONL — minimal user + assistant exchange
    transcript_lines = [
        json.dumps(
            {
                'type': 'user',
                'message': {
                    'role': 'user',
                    'content': 'Hello, this is a smoke test session.',
                },
                'timestamp': '2024-01-01T00:00:00.000Z',
                'cwd': '/test/project',
            }
        ),
        json.dumps(
            {
                'type': 'assistant',
                'message': {
                    'role': 'assistant',
                    'content': 'Hello! How can I help you today?',
                    'model': 'claude-3-opus-20240229',
                    'usage': {
                        'input_tokens': 10,
                        'output_tokens': 20,
                        'cache_read_input_tokens': 0,
                        'cache_creation_input_tokens': 0,
                    },
                },
                'timestamp': '2024-01-01T00:00:01.000Z',
            }
        ),
    ]
    transcript_file = project_dir / 'smoke-test-session-001.jsonl'
    transcript_file.write_text('\n'.join(transcript_lines) + '\n', encoding='utf-8')


def _create_codex_fixture(data_dir: Path) -> None:
    """Create minimal Codex fixture: 1 top-level thread + 1 subagent thread.

    Codex uses state_5.sqlite with threads table. Subagent threads should
    NOT be counted as top-level sessions.
    """
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create state_5.sqlite with threads table
    db_path = data_dir / 'state_5.sqlite'
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                parent_thread_id TEXT,
                title TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Top-level thread
        conn.execute(
            """INSERT INTO threads (id, parent_thread_id, title, created_at, updated_at)
               VALUES ('top-level-thread-001', NULL, 'Top Level Session',
                       '2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z')"""
        )
        # Subagent thread — should NOT be counted
        conn.execute(
            """INSERT INTO threads (id, parent_thread_id, title, created_at, updated_at)
               VALUES ('subagent-thread-001', 'top-level-thread-001', 'Subagent Session',
                       '2024-01-01T00:00:00Z', '2024-01-01T00:00:01Z')"""
        )
        conn.commit()
    finally:
        conn.close()

    # session_index.jsonl — index entries for both threads
    index_lines = [
        json.dumps(
            {
                'thread_id': 'top-level-thread-001',
                'parent_thread_id': None,
                'title': 'Top Level Session',
            }
        ),
        json.dumps(
            {
                'thread_id': 'subagent-thread-001',
                'parent_thread_id': 'top-level-thread-001',
                'title': 'Subagent Session',
            }
        ),
    ]
    (data_dir / 'session_index.jsonl').write_text('\n'.join(index_lines) + '\n', encoding='utf-8')

    # Create rollout files for each thread
    threads_dir = data_dir / 'threads'
    threads_dir.mkdir(parents=True, exist_ok=True)

    top_dir = threads_dir / 'top-level-thread-001'
    top_dir.mkdir(parents=True, exist_ok=True)
    (top_dir / 'rollout.jsonl').write_text(
        json.dumps({'type': 'system', 'timestamp': '2024-01-01T00:00:00Z'}) + '\n',
        encoding='utf-8',
    )

    sub_dir = threads_dir / 'subagent-thread-001'
    sub_dir.mkdir(parents=True, exist_ok=True)
    (sub_dir / 'rollout.jsonl').write_text(
        json.dumps({'type': 'system', 'timestamp': '2024-01-01T00:00:00Z'}) + '\n',
        encoding='utf-8',
    )


def _create_qoder_fixture(data_dir: Path) -> None:
    """Create empty Qoder directory — should result in 0 sessions."""
    data_dir.mkdir(parents=True, exist_ok=True)


# ─── Pytest fixtures ───────────────────────────────────────────────


def _isolated_environment(tmp_path: Path):
    """Create isolated environment with tmp fixtures for all three agents.

    Returns a dict with env vars and paths for the test.
    """
    home_dir = tmp_path / 'test home'
    home_dir.mkdir()
    claude_dir = home_dir / '.claude'
    codex_dir = home_dir / '.codex'
    qoder_dir = home_dir / '.qoder'
    index_dir = tmp_path / 'index'

    _create_claude_fixture(claude_dir)
    _create_codex_fixture(codex_dir)
    _create_qoder_fixture(qoder_dir)

    env = os.environ.copy()
    env['HOME'] = str(home_dir)
    # JVM 不保证跟随 HOME；显式设置临时主目录，兼容带空格的路径。
    env['JAVA_OPTS'] = f'"-Duser.home={home_dir}"'
    for option in ('APP_CLI_OPTS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
        env[option] = ''
    env['INDEX_DIR'] = str(index_dir)
    env['SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS'] = '0'

    return env, index_dir


def test_scan_public_entry_state_flow(tmp_path: Path):
    """Cover public scan modes and filtering in one isolated index lifecycle."""
    env, index = _isolated_environment(tmp_path)
    db = index / 'index.sqlite'

    def run(*args):
        result = subprocess.run(
            ['bash', str(SCRIPT_PATH), 'scan', *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f'scan {args} failed: {result.stdout}\n{result.stderr}'
        return result.stdout

    def source_state(agent):
        with sqlite3.connect(db) as conn:
            rows = conn.execute(
                'SELECT * FROM sessions WHERE agent = ? ORDER BY session_key', (agent,)
            ).fetchall()
            artifacts = conn.execute(
                'SELECT a.* FROM session_artifacts a JOIN sessions s USING(session_key) '
                'WHERE s.agent = ? ORDER BY a.session_key,a.artifact_type',
                (agent,),
            ).fetchall()
            version = conn.execute(
                "SELECT value FROM index_metadata WHERE key = 'scan_logic_version'"
            ).fetchone()
            assert version is not None
            return rows, artifacts, version

    full = run('--full')
    assert all(
        item in full
        for item in (
            'Starting full scan',
            'Scan complete',
            'Claude Code: 1',
            'Codex:       1',
            'Total:       2',
        )
    ), full
    assert len(source_state('claude_code')[0]) == 1
    assert len(source_state('codex')[0]) == 1  # Codex subagent is excluded.

    incremental = run('--incremental')
    assert 'Starting incremental scan' in incremental and 'Incremental scan complete' in incremental

    for agent, expected in (('claude_code', 'Claude Code: 1'), ('codex', 'Codex:       1')):
        unselected = 'codex' if agent == 'claude_code' else 'claude_code'
        before = source_state(unselected)
        assert len(before[0]) == 1
        filtered = run('--full', '--agent', agent)
        assert all(item in filtered for item in ('Starting full scan', expected, 'Total:       1'))
        assert source_state(unselected) == before, f'{agent} filter changed {unselected}'
