"""Re-exports，用于 所有 Qoder session parsing functions.

This package splits the original qoder.py into:
- utils: interval merging, token estimation, timestamp helpers, text extraction
- model_config: model name resolution from Qoder app support directory
- discovery: session file discovery and canonical ID mapping
- parse: main parsing entry points (parse_session_detail, scan_all_sessions)

All public symbols are re-exported here so that
`from session_browser.sources.qoder import ...` continues to work
via the qoder.py facade.
"""

from __future__ import annotations

# 说明：Re-export config constants that were originally imported in qoder.py
from session_browser.config import QODER_DATA_DIR

# 说明：utils
from session_browser.sources.qoder_parts.utils import (
    _merge_intervals,
    _cap_text,
    _count_tokens,
    normalize_timestamp,
    _ts_ms_to_iso,
    _scan_project_dirs,
    _assistant_message_key,
    _merge_usage_dicts,
    _normalize_qoder_provider_usage,
    _extract_qoder_model,
    _assistant_records,
    _extract_user_text,
    _summarize_text,
    _extract_readable_title,
    _stringify_tool_result,
    _tool_result_looks_failed,
    _extract_event_text,
    _estimate_tokens_from_events,
    _ESTIMATE_TEXT_CAP,
)

# 说明：model_config
from session_browser.sources.qoder_parts.model_config import (
    _qoder_app_support_dir,
    _load_qoder_custom_model_names,
    _load_qoder_model_selector_names,
    _load_qoder_auth_model_names,
    _resolve_qoder_model_config_name,
    _load_qoder_current_assistant_model,
    _build_qoder_session_model_map,
    _infer_qoder_model_for_session,
)

# 说明：discovery
from session_browser.sources.qoder_parts.discovery import (
    _url_decode_path,
    _extract_cwd_from_events,
    _discover_sessions,
    _discover_cache_sessions,
    _build_canonical_id_map,
)

# 说明：parse
from session_browser.sources.qoder_parts.parse import (
    parse_session_detail,
    parse_session_detail_normalized,
    parse_normalized_session_file,
    build_normalized_session,
    scan_all_sessions,
    _find_session_file,
    _empty_session,
    _build_summary_from_events,
    _extract_messages,
    _fill_estimates,
    _extract_tool_calls,
    _parse_cache_session,
)

__all__ = [
    # 说明：config
    "QODER_DATA_DIR",
    # 说明：utils
    "_merge_intervals",
    "_cap_text",
    "_count_tokens",
    "normalize_timestamp",
    "_ts_ms_to_iso",
    "_scan_project_dirs",
    "_assistant_message_key",
    "_merge_usage_dicts",
    "_normalize_qoder_provider_usage",
    "_extract_qoder_model",
    "_assistant_records",
    "_extract_user_text",
    "_summarize_text",
    "_extract_readable_title",
    "_stringify_tool_result",
    "_tool_result_looks_failed",
    "_extract_event_text",
    "_estimate_tokens_from_events",
    "_ESTIMATE_TEXT_CAP",
    # 说明：model_config
    "_qoder_app_support_dir",
    "_load_qoder_custom_model_names",
    "_load_qoder_model_selector_names",
    "_load_qoder_auth_model_names",
    "_resolve_qoder_model_config_name",
    "_load_qoder_current_assistant_model",
    "_build_qoder_session_model_map",
    "_infer_qoder_model_for_session",
    # 说明：discovery
    "_url_decode_path",
    "_extract_cwd_from_events",
    "_discover_sessions",
    "_discover_cache_sessions",
    "_build_canonical_id_map",
    # 说明：parse
    "parse_session_detail",
    "parse_session_detail_normalized",
    "parse_normalized_session_file",
    "build_normalized_session",
    "scan_all_sessions",
    "_find_session_file",
    "_empty_session",
    "_build_summary_from_events",
    "_extract_messages",
    "_fill_estimates",
    "_extract_tool_calls",
    "_parse_cache_session",
]
