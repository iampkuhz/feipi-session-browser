"""Read redacted Qoder model-policy files for attribution evidence.

Agent-app collectors call this only with an explicit policy path, typically a
fixture or caller-approved file. It avoids account-wide discovery, redacts
credential-like keys, and returns one Evidence row for the parsed policy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from session_browser.attribution.core.models import ContentRef, Evidence

logger = logging.getLogger(__name__)


def read_model_policy(
    policy_path: str | Path | None = None,
    evidence_counter: int = 0,
) -> Evidence | None:
    """Read an explicit Qoder model-policy JSON file as Evidence.

    Agent-app attribution collection calls this when a policy fixture or
    approved path is available. Missing paths, unreadable files, and malformed
    JSON are treated as absent evidence and logged at debug level.

    Args:
        policy_path: Explicit policy JSON path; ``None`` disables collection so
            real user account locations are not probed.
        evidence_counter: Offset used to build a deterministic Evidence ID.

    Returns:
        Redacted model-policy Evidence, or ``None`` when no readable policy is
        available.
    """
    if not policy_path:
        return None

    path = Path(policy_path)
    try:
        if not path.exists() or not path.is_file():
            return None

        text = path.read_text(encoding='utf-8', errors='replace')
        data = json.loads(text)
        safe_data = _redact_sensitive(data)

        return Evidence(
            evidence_id=f'qoder_model_policy_{evidence_counter}',
            scope='agent_app',
            kind='model_policy',
            source_path=str(path),
            content_ref=ContentRef(
                kind='file_slice',
                pointer=str(path),
                preview=str(safe_data)[:200],
                can_load_full=True,
                redaction_applied=True,
            ),
            text_preview=str(safe_data)[:200],
            precision='extracted',
            confidence=0.7,
        )
    except (OSError, PermissionError, json.JSONDecodeError) as exc:
        logger.debug('无法读取 model policy %s: %s', path, exc)
        return None


def _redact_sensitive(data: dict) -> dict:
    """Redact credential-like keys in a parsed Qoder model policy.

    ``read_model_policy`` calls this before storing previews in Evidence.
    Dictionaries are copied recursively while non-sensitive values are preserved.

    Args:
        data: Parsed JSON object from the policy file.

    Returns:
        New dictionary with token, key, and credential values redacted.
    """
    sensitive = frozenset({'token', 'api_key', 'secret', 'password', 'credential'})
    result = {}
    for k, v in data.items():
        if k.lower() in sensitive:
            result[k] = '***REDACTED***'
        elif isinstance(v, dict):
            result[k] = _redact_sensitive(v)
        else:
            result[k] = v
    return result
