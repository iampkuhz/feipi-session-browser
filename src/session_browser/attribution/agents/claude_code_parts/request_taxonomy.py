"""Claude Code request attribution bucket-to-taxonomy mapping."""

from __future__ import annotations


REQUEST_BUCKET_CATEGORY_MAP = {
    "current_user_message": "current_user_input",
    "preceding_tool_results": "tool_result_context",
    "full_messages_array": "conversation_messages",
    "tool_schemas": "tool_definitions",
    "tool_definitions": "tool_definitions",
    "local_instruction_context": "local_instruction_context",
    "project_instruction_files": "project_instruction_files",
    "agent_subagent_prompt": "agent_subagent_prompt",
    "custom_agent_profile": "custom_agent_profile",
    "mcp_tool_metadata": "mcp_tool_metadata",
    "skill_plugin_catalog": "skill_plugin_catalog",
    "top_level_system_estimate": "builtin_system_prompt",
    "hidden_builtin_system_estimate": "builtin_system_prompt",
    "hidden_instruction_estimate": "hidden_instruction_estimate",
    "repository_file_context": "repository_file_context",
    "provider_wrapper_estimate": "runtime_wrapper_overhead",
    "unlocated_residual": "unlocated_residual",
}


__all__ = ["REQUEST_BUCKET_CATEGORY_MAP"]
