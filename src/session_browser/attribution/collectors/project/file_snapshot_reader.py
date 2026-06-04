"""文件快照读取器：读取项目文件快照作为 Evidence。"""

from __future__ import annotations

import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 8192


def read_file_snapshot(
    file_path: str | Path,
    kind: str = "file_snapshot",
    evidence_counter: int = 0,
) -> Evidence | None:
    """读取文件内容作为 Evidence。"""
    path = Path(file_path)

    try:
        if not path.exists() or not path.is_file():
            return None

        text = path.read_text(encoding="utf-8", errors="replace")
        text = text[:_MAX_FILE_SIZE]
        safe_text = _redact_sensitive(text)

        return Evidence(
            evidence_id=f"file_snapshot_{evidence_counter}",
            scope="project_repo",
            kind=kind,
            source_path=str(path),
            content_ref=ContentRef(
                kind="file_slice",
                pointer=str(path),
                preview=safe_text[:200],
                can_load_full=True,
                redaction_applied=True,
            ),
            text_preview=safe_text[:200],
            precision="extracted",
            confidence=0.85,
        )
    except (OSError, PermissionError) as exc:
        logger.debug("无法读取文件 %s: %s", path, exc)
        return None


def _redact_sensitive(text: str) -> str:
    import re
    sensitive_keys = frozenset({
        "api_key", "apikey", "token", "secret", "password",
        "authorization", "credential", "bearer",
    })
    for key in sensitive_keys:
        pattern = re.compile(
            rf'("{key}"\s*:\s*)"([^"]*)"',
            re.IGNORECASE,
        )
        text = pattern.sub(r'\1"***REDACTED***"', text)
    return text
