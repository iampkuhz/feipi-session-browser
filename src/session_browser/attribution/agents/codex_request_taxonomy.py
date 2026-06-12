"""Codex request attribution bucket-to-taxonomy mapping."""

from __future__ import annotations


REQUEST_BUCKET_CATEGORY_MAP = {
    "instructions": "instruction_context",
    "current_user_instruction": "current_user_input",
    "conversation_history": "conversation_messages",
    "provider_cached_context": "provider_cache_read_context",
    "previous_response_state": "provider_conversation_state",
    "tool_outputs": "tool_result_context",
    "captured_context_fragment": "captured_runtime_context",
    "repository_file_context": "captured_runtime_context",
    "tool_schemas": "tool_definitions",
    "reasoning_config": "reasoning_config",
    "provider_wrapper_overhead": "runtime_wrapper_overhead",
    "unknown_overhead": "unlocated_residual",
}


__all__ = ["REQUEST_BUCKET_CATEGORY_MAP"]
