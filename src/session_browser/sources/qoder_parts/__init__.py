"""Source adapter helpers for reading local agent session data.

Scanner and route code call this module to discover and normalize records.
It keeps raw parsing behavior unchanged.
"""

from __future__ import annotations

# 说明:Re-export config constants that were originally imported in qoder.py
from session_browser.config import QODER_DATA_DIR

# 说明:discovery
from session_browser.sources.qoder_parts.discovery import (
    _build_canonical_id_map,
    _discover_cache_sessions,
    _discover_sessions,
    _extract_cwd_from_events,
    _url_decode_path,
)

# 说明:model_config
from session_browser.sources.qoder_parts.model_config import (
    _build_qoder_session_model_map,
    _infer_qoder_model_for_session,
    _load_qoder_auth_model_names,
    _load_qoder_current_assistant_model,
    _load_qoder_custom_model_names,
    _load_qoder_model_selector_names,
    _qoder_app_support_dir,
    _resolve_qoder_model_config_name,
)

# 说明:parse
from session_browser.sources.qoder_parts.parse import (
    _build_summary_from_events,
    _empty_session,
    _extract_messages,
    _extract_tool_calls,
    _fill_estimates,
    _find_session_file,
    _parse_cache_session,
    build_normalized_session,
    parse_normalized_session_file,
    parse_session_detail,
    parse_session_detail_normalized,
    scan_all_sessions,
)

# 说明:utils
from session_browser.sources.qoder_parts.utils import (
    _ESTIMATE_TEXT_CAP,
    _assistant_message_key,
    _assistant_records,
    _cap_text,
    _count_tokens,
    _estimate_tokens_from_events,
    _extract_event_text,
    _extract_qoder_model,
    _extract_readable_title,
    _extract_user_text,
    _merge_intervals,
    _merge_usage_dicts,
    _normalize_qoder_provider_usage,
    _scan_project_dirs,
    _stringify_tool_result,
    _summarize_text,
    _tool_result_looks_failed,
    _ts_ms_to_iso,
    normalize_timestamp,
)

__all__ = [
    # 说明:config
    'QODER_DATA_DIR',
    '_ESTIMATE_TEXT_CAP',
    '_assistant_message_key',
    '_assistant_records',
    '_build_canonical_id_map',
    '_build_qoder_session_model_map',
    '_build_summary_from_events',
    '_cap_text',
    '_count_tokens',
    '_discover_cache_sessions',
    '_discover_sessions',
    '_empty_session',
    '_estimate_tokens_from_events',
    '_extract_cwd_from_events',
    '_extract_event_text',
    '_extract_messages',
    '_extract_qoder_model',
    '_extract_readable_title',
    '_extract_tool_calls',
    '_extract_user_text',
    '_fill_estimates',
    '_find_session_file',
    '_infer_qoder_model_for_session',
    '_load_qoder_auth_model_names',
    '_load_qoder_current_assistant_model',
    '_load_qoder_custom_model_names',
    '_load_qoder_model_selector_names',
    # 说明:utils
    '_merge_intervals',
    '_merge_usage_dicts',
    '_normalize_qoder_provider_usage',
    '_parse_cache_session',
    # 说明:model_config
    '_qoder_app_support_dir',
    '_resolve_qoder_model_config_name',
    '_scan_project_dirs',
    '_stringify_tool_result',
    '_summarize_text',
    '_tool_result_looks_failed',
    '_ts_ms_to_iso',
    # 说明:discovery
    '_url_decode_path',
    'build_normalized_session',
    'normalize_timestamp',
    'parse_normalized_session_file',
    # 说明:parse
    'parse_session_detail',
    'parse_session_detail_normalized',
    'scan_all_sessions',
]
