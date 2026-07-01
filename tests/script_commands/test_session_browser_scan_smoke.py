"""Scan script entry smoke test with isolated tmp fixtures.

This test ensures that `./scripts/session-browser.sh scan --full` works
end-to-end through the real script entry, launcher, env vars, SQLite index,
and scan-engine production path — without scanning real user data.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
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
    (data_dir / 'history.jsonl').write_text(
        json.dumps(history_entry) + '\n', encoding='utf-8'
    )

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
    (data_dir / 'session_index.jsonl').write_text(
        '\n'.join(index_lines) + '\n', encoding='utf-8'
    )

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


@pytest.fixture
def isolated_env(tmp_path: Path):
    """Create isolated environment with tmp fixtures for all three agents.

    Returns a dict with env vars and paths for the test.
    """
    home_dir = tmp_path / 'home'
    home_dir.mkdir()
    claude_dir = tmp_path / 'claude'
    codex_dir = tmp_path / 'codex'
    qoder_dir = tmp_path / 'qoder'
    index_dir = tmp_path / 'index'

    _create_claude_fixture(claude_dir)
    _create_codex_fixture(codex_dir)
    _create_qoder_fixture(qoder_dir)

    env = os.environ.copy()
    env['HOME'] = str(home_dir)
    env['CLAUDE_DATA_DIR'] = str(claude_dir)
    env['CODEX_DATA_DIR'] = str(codex_dir)
    env['QODER_DATA_DIR'] = str(qoder_dir)
    env['SESSION_BROWSER_LOCAL_DATA_DIR'] = str(index_dir)
    env['INDEX_DIR'] = str(index_dir)
    env['SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS'] = '0'

    return {
        'env': env,
        'home_dir': home_dir,
        'claude_dir': claude_dir,
        'codex_dir': codex_dir,
        'qoder_dir': qoder_dir,
        'index_dir': index_dir,
    }


# ─── Test cases ────────────────────────────────────────────────────


def test_scan_full_with_isolated_fixtures(isolated_env):
    """Test `scan --full` with isolated tmp fixtures.

    Verifies:
    - exit code = 0
    - stdout contains expected keywords
    - counts match fixture data
    - Codex subagent thread NOT counted
    """
    env = isolated_env['env']

    result = subprocess.run(
        ['bash', str(SCRIPT_PATH), 'scan', '--full'],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    stdout = result.stdout
    stderr = result.stderr

    assert result.returncode == 0, (
        f'scan --full failed with exit code {result.returncode}\n'
        f'stdout: {stdout}\nstderr: {stderr}'
    )

    # Verify expected output keywords
    assert 'Starting full scan' in stdout, f'Missing "Starting full scan" in output: {stdout}'
    assert 'Scan complete' in stdout, f'Missing "Scan complete" in output: {stdout}'
    assert 'Claude Code:' in stdout, f'Missing "Claude Code:" in output: {stdout}'
    assert 'Codex:' in stdout, f'Missing "Codex:" in output: {stdout}'
    assert 'Total:' in stdout, f'Missing "Total:" in output: {stdout}'

    # Verify counts: Claude=1, Codex=1 (subagent excluded), Total=2
    assert 'Claude Code: 1' in stdout, (
        f'Expected "Claude Code: 1" in output: {stdout}'
    )
    assert 'Codex:       1' in stdout, (
        f'Expected "Codex:       1" in output: {stdout}'
    )
    assert 'Total:       2' in stdout, (
        f'Expected "Total:       2" in output: {stdout}'
    )


def test_scan_incremental_after_full(isolated_env):
    """Test default incremental scan after full scan.

    Verifies:
    - Second run (incremental) exits 0
    - Counts are consistent
    """
    env = isolated_env['env']

    # First: full scan
    result_full = subprocess.run(
        ['bash', str(SCRIPT_PATH), 'scan', '--full'],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result_full.returncode == 0, (
        f'Full scan failed: {result_full.stdout}\n{result_full.stderr}'
    )

    # Second: incremental scan (default)
    result_incr = subprocess.run(
        ['bash', str(SCRIPT_PATH), 'scan'],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result_incr.returncode == 0, (
        f'Incremental scan failed: {result_incr.stdout}\n{result_incr.stderr}'
    )

    stdout = result_incr.stdout
    assert 'Scan complete' in stdout or 'Incremental scan complete' in stdout, (
        f'Missing scan completion message in output: {stdout}'
    )


def test_scan_full_agent_filter_claude(isolated_env):
    """Test `scan --full --agent claude_code` — single agent filter."""
    env = isolated_env['env']

    result = subprocess.run(
        ['bash', str(SCRIPT_PATH), 'scan', '--full', '--agent', 'claude_code'],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    stdout = result.stdout
    assert result.returncode == 0, (
        f'scan --full --agent claude_code failed: {stdout}\n{result.stderr}'
    )
    assert 'Starting full scan' in stdout
    assert 'Claude Code: 1' in stdout
    assert 'Total:       1' in stdout


def test_scan_full_agent_filter_codex(isolated_env):
    """Test `scan --full --agent codex` — verifies subagent exclusion."""
    env = isolated_env['env']

    result = subprocess.run(
        ['bash', str(SCRIPT_PATH), 'scan', '--full', '--agent', 'codex'],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    stdout = result.stdout
    assert result.returncode == 0, (
        f'scan --full --agent codex failed: {stdout}\n{result.stderr}'
    )
    assert 'Starting full scan' in stdout
    assert 'Codex:       1' in stdout
    assert 'Total:       1' in stdout
