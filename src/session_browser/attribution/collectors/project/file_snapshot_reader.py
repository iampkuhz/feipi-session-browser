"""Read bounded project-file snapshots for attribution evidence.

Project attribution collectors call this module with explicit file paths chosen
by upstream discovery. It reads only local files, truncates large content,
redacts common credential assignments, and returns a single Evidence row.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 8192


def read_file_snapshot(
    file_path: str | Path,
    kind: str = 'file_snapshot',
    evidence_counter: int = 0,
) -> Evidence | None:
    """Read one project file as a redacted snapshot Evidence row.

    Project collectors call this after selecting a candidate context file. The
    function does not create files; it only reads the target path and logs debug
    details when the path is unavailable.

    Args:
        file_path: Explicit project file path selected for snapshot evidence.
        kind: Evidence kind to store on the returned row.
        evidence_counter: Offset used to build deterministic Evidence IDs.

    Returns:
        Redacted Evidence for the readable file, or ``None`` when the path is not
        a regular file or cannot be read.
    """
    path = Path(file_path)

    try:
        if not path.exists() or not path.is_file():
            return None

        text = path.read_text(encoding='utf-8', errors='replace')
        text = text[:_MAX_FILE_SIZE]
        safe_text = _redact_sensitive(text)

        return Evidence(
            evidence_id=f'file_snapshot_{evidence_counter}',
            scope='project_repo',
            kind=kind,
            source_path=str(path),
            content_ref=ContentRef(
                kind='file_slice',
                pointer=str(path),
                preview=safe_text[:200],
                can_load_full=True,
                redaction_applied=True,
            ),
            text_preview=safe_text[:200],
            precision='extracted',
            confidence=0.85,
        )
    except (OSError, PermissionError) as exc:
        logger.debug('无法读取文件 %s: %s', path, exc)
        return None


def _redact_sensitive(text: str) -> str:
    """Redact simple JSON-style credential values from file preview text.

    ``read_file_snapshot`` calls this before placing content in Evidence
    previews. The helper keeps the original text shape except for matched
    credential values and has no external side effects.

    Args:
        text: UTF-8 replacement-decoded file text, already bounded by size.

    Returns:
        Text with common secret-like JSON string values replaced.
    """
    sensitive_keys = frozenset(
        {
            'api_key',
            'apikey',
            'token',
            'secret',
            'password',
            'authorization',
            'credential',
            'bearer',
        }
    )
    for key in sensitive_keys:
        pattern = re.compile(
            rf'("{key}"\s*:\s*)"([^"]*)"',
            re.IGNORECASE,
        )
        text = pattern.sub(r'\1"***REDACTED***"', text)
    return text
