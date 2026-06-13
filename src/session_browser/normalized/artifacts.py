"""Persist normalized session JSON artifacts next to the SQLite index."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from session_browser.index.writers import upsert_session_artifact
from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION, validate_normalized_session


NORMALIZED_SESSION_ARTIFACT_TYPE = "normalized_session_json"
NORMALIZED_ARTIFACT_GENERATOR_VERSION = "normalized-session-artifact.v3"


def normalized_artifact_path(
    *,
    index_dir: str | Path,
    agent: str,
    session_id: str,
) -> Path:
    """Return the canonical path for one session's normalized JSON artifact."""
    safe_agent = _safe_path_component(agent)
    safe_session_id = _safe_path_component(session_id)
    return Path(index_dir) / "artifacts" / "normalized-sessions" / safe_agent / f"{safe_session_id}.json"


def write_normalized_session_artifact(
    normalized: dict[str, Any],
    *,
    index_dir: str | Path | None = None,
    validate: bool = True,
    pretty: bool = False,
    source_path: str = "",
    source_mtime: float = 0,
) -> tuple[Path, int]:
    """Write one normalized session JSON artifact atomically.

    Returns:
        ``(path, size_bytes)`` for DB association.
    """
    if validate:
        validate_normalized_session(normalized)

    from session_browser.config import INDEX_DIR, ensure_index_dir

    if index_dir is None:
        ensure_index_dir()
        target_index_dir = INDEX_DIR
    else:
        target_index_dir = Path(index_dir)
        target_index_dir.mkdir(parents=True, exist_ok=True)

    session = normalized.get("session") if isinstance(normalized.get("session"), dict) else {}
    agent = str(normalized.get("agent") or session.get("agent") or "unknown")
    session_id = str(session.get("session_id") or session.get("session_key") or "unknown")

    path = normalized_artifact_path(
        index_dir=target_index_dir,
        agent=agent,
        session_id=session_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    if pretty:
        payload = json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)
    size_bytes = path.stat().st_size
    _write_artifact_meta(
        path,
        schema_version=str(normalized.get("schema_version") or ""),
        source_path=source_path,
        source_mtime=source_mtime,
        size_bytes=size_bytes,
    )
    return path, size_bytes


def persist_normalized_session_artifact(
    conn,
    normalized: dict[str, Any],
    *,
    source_path: str = "",
    source_mtime: float = 0,
    index_dir: str | Path | None = None,
    validate: bool = True,
    pretty: bool = False,
) -> Path:
    """Write normalized JSON and upsert the DB association row."""
    path, size_bytes = write_normalized_session_artifact(
        normalized,
        index_dir=index_dir,
        validate=validate,
        pretty=pretty,
        source_path=source_path,
        source_mtime=source_mtime,
    )
    session = normalized.get("session") if isinstance(normalized.get("session"), dict) else {}
    session_key = str(session.get("session_key") or "")
    if not session_key:
        raise ValueError("normalized.session.session_key is required")

    upsert_session_artifact(
        conn,
        session_key=session_key,
        artifact_type=NORMALIZED_SESSION_ARTIFACT_TYPE,
        path=str(path),
        schema_version=str(normalized.get("schema_version") or ""),
        source_path=source_path,
        source_mtime=source_mtime,
        size_bytes=size_bytes,
    )
    return path


def persist_current_normalized_session_artifact_reference(
    conn,
    *,
    session_key: str,
    source_path: str,
    source_mtime: float,
    index_dir: str | Path | None = None,
) -> Path | None:
    """Upsert DB row for a current on-disk artifact, if its sidecar matches."""
    agent, session_id = _split_session_key(session_key)
    if not agent or not session_id:
        return None

    from session_browser.config import INDEX_DIR

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
    if int(meta.get("size_bytes") or 0) != size_bytes:
        return None

    upsert_session_artifact(
        conn,
        session_key=session_key,
        artifact_type=NORMALIZED_SESSION_ARTIFACT_TYPE,
        path=str(path),
        schema_version=str(meta.get("schema_version") or NORMALIZED_SCHEMA_VERSION),
        source_path=source_path,
        source_mtime=source_mtime,
        size_bytes=size_bytes,
    )
    return path


def read_normalized_session_artifact(path: str | Path) -> dict[str, Any]:
    """Read a normalized session JSON artifact from disk."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("normalized artifact must contain a JSON object")
    return data


def _safe_path_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "unknown")).strip("._-")
    return (safe or "unknown")[:180]


def _artifact_meta_path(path: str | Path) -> Path:
    artifact_path = Path(path)
    return artifact_path.with_suffix(artifact_path.suffix + ".meta.json")


def _write_artifact_meta(
    path: Path,
    *,
    schema_version: str,
    source_path: str,
    source_mtime: float,
    size_bytes: int,
) -> None:
    source_size = 0
    if source_path:
        source = Path(source_path)
        if source.exists():
            source_size = source.stat().st_size
    meta = {
        "artifact_type": NORMALIZED_SESSION_ARTIFACT_TYPE,
        "generator_version": NORMALIZED_ARTIFACT_GENERATOR_VERSION,
        "schema_version": schema_version,
        "source_path": source_path,
        "source_mtime": source_mtime,
        "source_size": source_size,
        "size_bytes": size_bytes,
        "generated_at": time.time(),
    }
    meta_path = _artifact_meta_path(path)
    tmp_path = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(meta_path)


def _read_artifact_meta(path: str | Path) -> dict[str, Any]:
    meta_path = _artifact_meta_path(path)
    if not meta_path.exists():
        return {}
    try:
        with meta_path.open("r", encoding="utf-8") as f:
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
    if not meta:
        return False
    if meta.get("artifact_type") != NORMALIZED_SESSION_ARTIFACT_TYPE:
        return False
    if meta.get("generator_version") != NORMALIZED_ARTIFACT_GENERATOR_VERSION:
        return False
    if meta.get("schema_version") != NORMALIZED_SCHEMA_VERSION:
        return False
    if meta.get("source_path") != source_path:
        return False
    try:
        if abs(float(meta.get("source_mtime") or 0) - float(source_mtime or 0)) > 1e-6:
            return False
    except (TypeError, ValueError):
        return False
    if source_path:
        source = Path(source_path)
        if not source.exists():
            return False
        if int(meta.get("source_size") or 0) != source.stat().st_size:
            return False
    return True


def _split_session_key(session_key: str) -> tuple[str, str]:
    if ":" not in session_key:
        return "", ""
    agent, session_id = session_key.split(":", 1)
    return agent, session_id
