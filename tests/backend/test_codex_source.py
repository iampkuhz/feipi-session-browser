"""Tests for Codex parser."""

import json
from pathlib import Path


def test_parse_session_index_empty_when_missing():
    """Test that parse_session_index returns empty when no data dir."""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            result = codex.parse_session_index()
            assert result == []
        finally:
            codex.CODEX_DATA_DIR = original


def test_read_threads_db_empty_when_missing():
    """Test that read_threads_db returns empty when no DB."""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            result = codex.read_threads_db()
            assert result == {}
        finally:
            codex.CODEX_DATA_DIR = original


def test_session_file_search():
    """Test that _find_session_file walks the hierarchy."""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            # Create a fake session file
            session_dir = Path(tmpdir) / "sessions" / "2026" / "03" / "28"
            session_dir.mkdir(parents=True)
            session_file = session_dir / "rollout-2026-03-28T15-54-11-019d336f.jsonl"
            session_file.touch()

            result = codex._find_session_file("019d336f")
            assert result is not None
            assert result == session_file
        finally:
            codex.CODEX_DATA_DIR = original
