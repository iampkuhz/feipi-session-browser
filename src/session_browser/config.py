"""session-browser 配置。

Fixed defaults for all paths. INDEX_DIR, SERVER_HOST, and SERVER_PORT
can be overridden via environment variables for shell/container handoff.
"""

from __future__ import annotations

import os
from pathlib import Path


def _home() -> Path:
    return Path.home()


# 说明：─── Data source paths ──────────────────────────────────────────────────

# Base directories，用于 agent session data.
# 说明：CLAUDE_DATA_DIR can be overridden via environment variable (used by tests).
CLAUDE_DATA_DIR = Path(os.environ.get("CLAUDE_DATA_DIR", str(_home() / ".claude")))
CODEX_DATA_DIR = Path(os.environ.get("CODEX_DATA_DIR", str(_home() / ".codex")))
QODER_DATA_DIR = Path(os.environ.get("QODER_DATA_DIR", str(_home() / ".qoder")))


# 说明：─── Index storage ───────────────────────────────────────────────────────

# 说明：SQLite index file location.
# Local foreground testing intentionally uses 一个 different default，来源于 Podman.
INDEX_DIR = Path(os.environ.get(
    "INDEX_DIR",
    str(_home() / ".local" / "share" / "feipi" / "session-browser" / "local-test-index"),
))
INDEX_PATH = INDEX_DIR / "index.sqlite"


def ensure_index_dir() -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


# 说明：─── Server ──────────────────────────────────────────────────────────────

SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "18999"))


# 说明：─── Logging / release metadata ─────────────────────────────────────────


def _default_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip() or "0.0-dev"
    except OSError:
        return "0.0-dev"


SESSION_BROWSER_VERSION = _default_version()
SESSION_BROWSER_LOG_LEVEL = "INFO"
