"""Configuration for session-browser.

All paths are configurable via environment variables for container compatibility.
Defaults point to the current user's home directory on macOS/Linux.
"""

from __future__ import annotations

import os
from pathlib import Path


def _home() -> Path:
    return Path.home()


# ─── Data source paths ──────────────────────────────────────────────────

# Base directories for agent session data
CLAUDE_DATA_DIR = Path(os.environ.get("CLAUDE_DATA_DIR", str(_home() / ".claude")))
CODEX_DATA_DIR = Path(os.environ.get("CODEX_DATA_DIR", str(_home() / ".codex")))
QODER_DATA_DIR = Path(os.environ.get("QODER_DATA_DIR", str(_home() / ".qoder")))


# ─── Index storage ───────────────────────────────────────────────────────

# SQLite index file location.
# Local foreground testing intentionally uses a different default from Podman.
INDEX_DIR = Path(os.environ.get(
    "INDEX_DIR",
    str(_home() / ".local" / "share" / "feipi" / "session-browser" / "local-test-index"),
))
INDEX_PATH = INDEX_DIR / "index.sqlite"


def ensure_index_dir() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


# ─── Server ──────────────────────────────────────────────────────────────

SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "18999"))


# ─── Logging / release metadata ─────────────────────────────────────────


def _default_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0.0-dev"
    except OSError:
        return "0.0.0-dev"


SESSION_BROWSER_VERSION = os.environ.get("SESSION_BROWSER_VERSION", _default_version())
SESSION_BROWSER_LOG_LEVEL = os.environ.get("SESSION_BROWSER_LOG_LEVEL", "INFO").upper()
