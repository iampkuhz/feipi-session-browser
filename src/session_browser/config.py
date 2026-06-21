"""Environment-backed configuration for session-browser paths and metadata.

The CLI, indexer, and web server import this module at process startup. It
resolves agent data directories, the SQLite index location, server bind
defaults, and release metadata from environment variables while providing stable
local defaults for development and container handoff.
"""

from __future__ import annotations

import os
from pathlib import Path


def _home() -> Path:
    """Return the current user's home directory for default path construction.

    Returns:
        ``Path.home()`` as a ``Path`` for composing default data directories.
    """
    return Path.home()


# Data source paths.
# Base directories for agent session data; CLAUDE_DATA_DIR is test-overridable.
CLAUDE_DATA_DIR = Path(os.environ.get('CLAUDE_DATA_DIR', str(_home() / '.claude')))
CODEX_DATA_DIR = Path(os.environ.get('CODEX_DATA_DIR', str(_home() / '.codex')))
QODER_DATA_DIR = Path(os.environ.get('QODER_DATA_DIR', str(_home() / '.qoder')))


# Index storage.
# Local foreground testing intentionally uses a different default than Podman.
INDEX_DIR = Path(
    os.environ.get(
        'INDEX_DIR',
        str(_home() / '.local' / 'share' / 'feipi' / 'session-browser' / 'local-test-index'),
    )
)
INDEX_PATH = INDEX_DIR / 'index.sqlite'


def ensure_index_dir() -> None:
    """Create the configured index directory before opening SQLite files.

    Side Effects:
        Creates ``INDEX_DIR`` and any missing parents. Existing directories are
        left untouched so repeated CLI startup and scan lock acquisition are
        idempotent.
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)


# Server.

SERVER_HOST = os.environ.get('SERVER_HOST', '127.0.0.1')
SERVER_PORT = int(os.environ.get('SERVER_PORT', '18999'))


# Logging and release metadata.


def _default_version() -> str:
    """Load the package version from the repository ``VERSION`` file.

    Returns:
        Trimmed version text, or ``0.0-dev`` when the file is absent, unreadable,
        or empty.
    """
    version_file = Path(__file__).resolve().parents[2] / 'VERSION'
    try:
        return version_file.read_text(encoding='utf-8').strip() or '0.0-dev'
    except OSError:
        return '0.0-dev'


SESSION_BROWSER_VERSION = _default_version()
SESSION_BROWSER_LOG_LEVEL = 'INFO'
