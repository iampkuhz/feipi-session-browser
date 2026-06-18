"""Qoder request attribution bucket-to-taxonomy mapping."""

from __future__ import annotations


REQUEST_BUCKET_CATEGORY_MAP = {
    "full_messages_array": "conversation_messages",
    "history_messages": "conversation_messages",
    "captured_context_fragment": "captured_runtime_context",
    "tool_results": "tool_result_context",
    "current_user_message": "current_user_input",
    "local_instruction_context": "local_instruction_context",
    "project_instruction_files": "project_instruction_files",
    "custom_agent_profile": "custom_agent_profile",
    "repository_file_context": "repository_file_context",
    "tool_schemas": "tool_definitions",
    "tool_definitions": "tool_definitions",
    "qoder_runtime_context_estimate": "runtime_wrapper_overhead",
    "unknown_overhead": "unlocated_residual",
}


__all__ = ["REQUEST_BUCKET_CATEGORY_MAP"]
