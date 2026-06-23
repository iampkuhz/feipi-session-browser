"""Normalized session artifact 只读 consumer 与路径解析。

Java 是 canonical normalized JSON/meta 唯一 producer。
本模块只提供路径计算、sidecar 读取和 freshness 校验，不包含任何写入 API。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from session_browser.config import INDEX_DIR
from session_browser.index.writers import upsert_session_artifact
from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION

if TYPE_CHECKING:
    import sqlite3

NORMALIZED_SESSION_ARTIFACT_TYPE = 'normalized_session_json'
# Java 已成为 canonical producer；此常量仅用于 reader freshness check，
# 检测旧 Python-produced artifact 的 sidecar 是否过期。
NORMALIZED_ARTIFACT_GENERATOR_VERSION = 'normalized-session-artifact.v6'
_MTIME_TOLERANCE_SECONDS = 1e-6


def normalized_artifact_path(
    *,
    index_dir: str | Path,
    agent: str,
    session_id: str,
) -> Path:
    """Build the deterministic artifact path for one normalized session.

    The artifact writer and stale-reference repair path call this helper before
    any filesystem write. It sanitizes agent and session identifiers so the
    normalized JSON stays under ``index_dir/artifacts/normalized-sessions``.

    Args:
        index_dir: Root directory that owns the SQLite index and artifact tree.
        agent: Source adapter name stored in the normalized artifact.
        session_id: Provider-local session identifier from the normalized
            session payload.

    Returns:
        Canonical path where the JSON artifact should be read or written.
    """
    safe_agent = _safe_path_component(agent)
    safe_session_id = _safe_path_component(session_id)
    return (
        Path(index_dir)
        / 'artifacts'
        / 'normalized-sessions'
        / safe_agent
        / f'{safe_session_id}.json'
    )


def persist_current_normalized_session_artifact_reference(
    conn: sqlite3.Connection,
    *,
    session_key: str,
    source_path: str,
    source_mtime: float,
    index_dir: str | Path | None = None,
) -> Path | None:
    """Upsert the SQLite row for an already-current on-disk artifact.

    Incremental scans call this when a normalized JSON artifact may already
    match the source transcript. It verifies sidecar freshness and only touches
    SQLite when the artifact still reflects ``source_path`` and ``source_mtime``.

    Args:
        conn: Open SQLite connection that receives the artifact association.
        session_key: Canonical ``agent:session_id`` key for the session row.
        source_path: Source transcript path that the sidecar must match.
        source_mtime: Source transcript modification time that the sidecar must
            match.
        index_dir: Optional artifact root; when omitted the configured
            ``INDEX_DIR`` is used.

    Returns:
        Current artifact path when the sidecar and file size match, otherwise
        ``None``. The only side effect is an SQLite upsert when a match exists.
    """
    path = find_current_normalized_session_artifact(
        session_key=session_key,
        source_path=source_path,
        source_mtime=source_mtime,
        index_dir=index_dir,
    )
    if path is None:
        return None
    meta = _read_artifact_meta(path)
    size_bytes = path.stat().st_size

    upsert_session_artifact(
        conn,
        session_key=session_key,
        artifact_type=NORMALIZED_SESSION_ARTIFACT_TYPE,
        path=str(path),
        schema_version=str(meta.get('schema_version') or NORMALIZED_SCHEMA_VERSION),
        source_path=source_path,
        source_mtime=source_mtime,
        size_bytes=size_bytes,
    )
    return path


def find_current_normalized_session_artifact(
    *,
    session_key: str,
    source_path: str,
    source_mtime: float,
    index_dir: str | Path | None = None,
) -> Path | None:
    """Find a fresh normalized artifact without writing SQLite rows.

    Stale-reference repair and incremental scans call this before deciding
    whether a normalized artifact must be regenerated. It checks the derived
    artifact path, metadata sidecar, source file size, and artifact size.

    Args:
        session_key: Canonical ``agent:session_id`` key used to derive the path.
        source_path: Source transcript path that the metadata sidecar must
            reference.
        source_mtime: Source transcript modification time that the sidecar must
            match.
        index_dir: Optional artifact root; when omitted the configured
            ``INDEX_DIR`` is used.

    Returns:
        Artifact path when all freshness checks pass, otherwise ``None``.
    """
    agent, session_id = _split_session_key(session_key)
    if not agent or not session_id:
        return None

    target_index_dir = Path(index_dir) if index_dir is not None else INDEX_DIR
    path = normalized_artifact_path(
        index_dir=target_index_dir,
        agent=agent,
        session_id=session_id,
    )
    meta = _read_artifact_meta(path)
    if not _artifact_meta_matches(
        meta,
        source_path=source_path,
        source_mtime=source_mtime,
    ):
        return None
    if not path.exists():
        return None
    size_bytes = path.stat().st_size
    if int(meta.get('size_bytes') or 0) != size_bytes:
        return None
    return path


def read_normalized_session_artifact(path: str | Path) -> dict[str, Any]:
    """Read one normalized session JSON artifact from disk.

    Query and debugging paths call this after resolving an artifact reference
    from SQLite. The function only decodes the JSON object and does not validate
    the semantic schema or mutate the artifact.

    Args:
        path: Filesystem path to a normalized JSON artifact.

    Returns:
        Decoded JSON object from the artifact file.

    Raises:
        ValueError: Raised when the JSON payload is not an object.
    """
    with Path(path).open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError('normalized artifact must contain a JSON object')
    return data


def _safe_path_component(value: str) -> str:
    """Sanitize one identifier for use as an artifact path component.

    Artifact path construction calls this helper for agent and session IDs. It
    replaces unsafe characters, trims empty punctuation-only values to
    ``unknown``, and caps the component length without touching the filesystem.

    Args:
        value: Raw provider identifier or fallback-like value.

    Returns:
        Path-safe component suitable for a filename or directory name.
    """
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value or 'unknown')).strip('._-')
    return (safe or 'unknown')[:180]


def _artifact_meta_path(path: str | Path) -> Path:
    """Derive the sidecar metadata path for an artifact JSON file.

    All freshness readers and writers call this helper so the sidecar suffix is
    stable. It performs no I/O and preserves the original artifact suffix.

    Args:
        path: JSON artifact path whose metadata sidecar is needed.

    Returns:
        Path ending in ``.json.meta.json`` for normalized session artifacts.
    """
    artifact_path = Path(path)
    return artifact_path.with_suffix(artifact_path.suffix + '.meta.json')


def _read_artifact_meta(path: str | Path) -> dict[str, Any]:
    """Read artifact sidecar metadata as a best-effort freshness input.

    Freshness checks call this helper before touching SQLite. Missing, invalid,
    or non-object metadata is treated as stale by returning an empty mapping.

    Args:
        path: JSON artifact path whose sidecar should be decoded.

    Returns:
        Metadata object from the sidecar, or an empty mapping when it is absent
        or unreadable.
    """
    meta_path = _artifact_meta_path(path)
    if not meta_path.exists():
        return {}
    try:
        with meta_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _artifact_meta_matches(
    meta: dict[str, Any],
    *,
    source_path: str,
    source_mtime: float,
) -> bool:
    """Check whether sidecar metadata still matches the source transcript.

    ``find_current_normalized_session_artifact`` calls this helper before
    trusting an existing JSON artifact. It compares artifact generator fields,
    source path, source mtime within a tiny filesystem tolerance, and source
    size when a source path is available.

    Args:
        meta: Decoded sidecar metadata object.
        source_path: Expected source transcript path.
        source_mtime: Expected source transcript modification time.

    Returns:
        ``True`` when the sidecar proves the artifact is current; otherwise
        ``False``.
    """
    expected_values = {
        'artifact_type': NORMALIZED_SESSION_ARTIFACT_TYPE,
        'generator_version': NORMALIZED_ARTIFACT_GENERATOR_VERSION,
        'schema_version': NORMALIZED_SCHEMA_VERSION,
        'source_path': source_path,
    }
    if not meta or any(meta.get(key) != value for key, value in expected_values.items()):
        return False
    try:
        if (
            abs(float(meta.get('source_mtime') or 0) - float(source_mtime or 0))
            > _MTIME_TOLERANCE_SECONDS
        ):
            return False
    except (TypeError, ValueError):
        return False
    if source_path:
        source = Path(source_path)
        if not source.exists():
            return False
        if int(meta.get('source_size') or 0) != source.stat().st_size:
            return False
    return True


def _split_session_key(session_key: str) -> tuple[str, str]:
    """Split a canonical session key into path lookup components.

    Artifact lookup calls this helper before deriving a normalized JSON path.
    Malformed keys are returned as empty components so callers can treat them as
    cache misses without raising.

    Args:
        session_key: Expected ``agent:session_id`` key from the session index.

    Returns:
        ``(agent, session_id)`` when the separator exists, otherwise
        ``('', '')``.
    """
    if ':' not in session_key:
        return '', ''
    agent, session_id = session_key.split(':', 1)
    return agent, session_id
