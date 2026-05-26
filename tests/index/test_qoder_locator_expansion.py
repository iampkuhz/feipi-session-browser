"""Qoder locator expansion tests.

Validates that _find_session_file and _locate_qoder_session_file correctly:
1. Resolve short ID alias -> full UUID, then search projects/.
2. Find full UUID sessions in projects/ (direct match + recursive).
3. Find sessions in cache/projects/ via recursive walk.
4. Handle empty/stale project_key (old index scenario).

Tests use monkeypatched tmp QODER_DATA_DIR — no real user data.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ─── Constants ──────────────────────────────────────────────────────────────

FULL_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
SHORT_ID = "a1b2c3d4"
PROJECT_NAME = "myproj"

# Minimal Qoder CLI JSONL (has timestamps, type field, usage)
CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/tmp/myproj",
        "entrypoint": "cli",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi!"}],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
]
CLI_JSONL_CONTENT = "\n".join(CLI_JSONL_LINES) + "\n"

# Minimal Qoder cache-format JSONL (no timestamps, role field)
CACHE_JSONL_LINES = [
    json.dumps({"role": "user", "message": {"content": "Hello from cache"}}),
    json.dumps({"role": "assistant", "message": {"content": [{"type": "text", "text": "Cache hi"}]}}),
]
CACHE_JSONL_CONTENT = "\n".join(CACHE_JSONL_LINES) + "\n"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_qoder_env(data_dir: str):
    """Set QODER_DATA_DIR and reload dependent modules."""
    old = os.environ.get("QODER_DATA_DIR", None)
    os.environ["QODER_DATA_DIR"] = data_dir

    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.config"):
            del sys.modules[_mod]
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.index.indexer"):
            del sys.modules[_mod]

    return old


def _restore_qoder_env(old: str | None):
    """Restore original QODER_DATA_DIR."""
    if old is not None:
        os.environ["QODER_DATA_DIR"] = old
    else:
        os.environ.pop("QODER_DATA_DIR", None)


def _reload_qoder_module():
    """Reload qoder source module after env change."""
    for _mod in list(sys.modules):
        if _mod == "session_browser.sources.qoder" or _mod.startswith("session_browser.sources.qoder"):
            del sys.modules[_mod]


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def full_uuid_in_projects(tmp_path: Path) -> Path:
    """Create projects/<project>/<FULL_UUID>.jsonl — CLI session."""
    data_dir = tmp_path / "qoder_data"
    projects_dir = data_dir / "projects" / PROJECT_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{FULL_UUID}.jsonl").write_text(CLI_JSONL_CONTENT)
    return data_dir


@pytest.fixture()
def short_id_in_cache_only(tmp_path: Path) -> Path:
    """Create cache/projects/<project>/conversation-history/<SHORT_ID>/<SHORT_ID>.jsonl
    WITHOUT a corresponding projects/ entry."""
    data_dir = tmp_path / "qoder_data"
    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / SHORT_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SHORT_ID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir


@pytest.fixture()
def both_full_and_short(tmp_path: Path) -> Path:
    """Create both projects/ (full UUID) and cache/ (short ID) for the same session."""
    data_dir = tmp_path / "qoder_data"
    projects_dir = data_dir / "projects" / PROJECT_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{FULL_UUID}.jsonl").write_text(CLI_JSONL_CONTENT)

    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / SHORT_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SHORT_ID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir


@pytest.fixture()
def cache_only_full_uuid(tmp_path: Path) -> Path:
    """Create only cache/projects/ with a full UUID session file (no projects/)."""
    data_dir = tmp_path / "qoder_data"
    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / FULL_UUID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{FULL_UUID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir


# ─── Tests: _find_session_file (qoder.py) ──────────────────────────────────

class TestFindSessionFile:
    """Tests for qoder._find_session_file."""

    def test_full_uuid_direct_match_in_projects(self, full_uuid_in_projects):
        """Full UUID session in projects/ should be found via direct match."""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, FULL_UUID)
            assert result is not None, "Should find full UUID session in projects/"
            assert result.name == f"{FULL_UUID}.jsonl"
            assert "projects" in str(result)
        finally:
            _restore_qoder_env(old)

    def test_short_id_resolved_to_full_uuid(self, both_full_and_short):
        """Short ID should resolve to full UUID and find the projects/ file."""
        data_dir = both_full_and_short
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None, "Short ID should resolve and find session"
            assert result.name == f"{FULL_UUID}.jsonl"
            # Should prefer projects/ over cache
            assert "projects" in str(result) and "cache" not in str(result).split("projects")[0].split("/")[-1:]
        finally:
            _restore_qoder_env(old)

    def test_cache_only_short_id_found(self, short_id_in_cache_only):
        """Session only in cache/ with short ID should still be locatable."""
        data_dir = short_id_in_cache_only
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None, "Should find cache-only session"
            assert result.name == f"{SHORT_ID}.jsonl"
            assert "cache" in str(result)
        finally:
            _restore_qoder_env(old)

    def test_empty_project_key_still_finds_session(self, full_uuid_in_projects):
        """When project_key is empty (old index), recursive search should find session."""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file("", FULL_UUID)
            assert result is not None, "Should find session even with empty project_key"
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)

    def test_cache_only_full_uuid_found(self, cache_only_full_uuid):
        """Full UUID session only in cache/ should be found via recursive walk."""
        data_dir = cache_only_full_uuid
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, FULL_UUID)
            assert result is not None, "Should find cache-only full UUID session"
            assert result.name == f"{FULL_UUID}.jsonl"
            assert "cache" in str(result)
        finally:
            _restore_qoder_env(old)

    def test_no_session_returns_none(self, tmp_path):
        """Non-existent session should return None, not raise."""
        data_dir = tmp_path / "qoder_empty"
        data_dir.mkdir(parents=True)
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, "nonexistent-uuid")
            assert result is None
        finally:
            _restore_qoder_env(old)


# ─── Tests: _locate_qoder_session_file (indexer.py) ────────────────────────

class TestLocateQoderSessionFile:
    """Tests for indexer._locate_qoder_session_file."""

    def test_full_uuid_in_projects(self, full_uuid_in_projects):
        """Locator should find full UUID session in projects/."""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file(PROJECT_NAME, FULL_UUID)
            assert result is not None
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)

    def test_short_id_resolved_in_indexer(self, both_full_and_short):
        """Indexer locator should also resolve short ID -> full UUID."""
        data_dir = both_full_and_short
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)

    def test_cache_fallback_in_indexer(self, short_id_in_cache_only):
        """Indexer locator should fall back to cache/ for cache-only sessions."""
        data_dir = short_id_in_cache_only
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None
            assert "cache" in str(result)
        finally:
            _restore_qoder_env(old)

    def test_empty_project_key_in_indexer(self, full_uuid_in_projects):
        """Indexer locator should find session even with empty project_key."""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file("", FULL_UUID)
            assert result is not None
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)
