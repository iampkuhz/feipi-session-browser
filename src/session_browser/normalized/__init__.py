"""Normalized session JSON 适配器。

The normalized layer is the intermediate contract between agent-specific
local logs and Session Detail presentation/import code.
"""

from session_browser.normalized.schema import (
    NORMALIZED_SCHEMA_VERSION,
    NormalizedValidationError,
    validate_normalized_session,
)
from session_browser.normalized.artifacts import (
    NORMALIZED_SESSION_ARTIFACT_TYPE,
    normalized_artifact_path,
    persist_normalized_session_artifact,
    read_normalized_session_artifact,
    write_normalized_session_artifact,
)

__all__ = [
    "NORMALIZED_SCHEMA_VERSION",
    "NORMALIZED_SESSION_ARTIFACT_TYPE",
    "NormalizedValidationError",
    "normalized_artifact_path",
    "persist_normalized_session_artifact",
    "read_normalized_session_artifact",
    "validate_normalized_session",
    "write_normalized_session_artifact",
]
