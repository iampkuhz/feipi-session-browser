"""Map Codex request attribution buckets to the shared taxonomy."""

from __future__ import annotations

REQUEST_BUCKET_CATEGORY_MAP = {
    'instructions': 'instruction_context',
    'platform_default_instructions': 'platform_default_instructions',
    'session_injected_instructions': 'session_injected_instructions',
    'skill_plugin_catalog': 'skill_plugin_catalog',
    'permission_sandbox_policy': 'permission_sandbox_policy',
    'client_app_context': 'client_app_context',
    'collaboration_mode_policy': 'collaboration_mode_policy',
    'runtime_environment_context': 'runtime_environment_context',
    'task_goal_context': 'task_goal_context',
    'current_user_instruction': 'current_user_input',
    'conversation_history': 'conversation_messages',
    'previous_response_state': 'provider_conversation_state',
    'tool_outputs': 'tool_result_context',
    'captured_context_fragment': 'captured_runtime_context',
    'repository_file_context': 'repository_file_context',
    'tool_schemas': 'tool_definitions',
    'tool_definitions': 'tool_definitions',
    'reasoning_config': 'reasoning_config',
    'provider_wrapper_overhead': 'runtime_wrapper_overhead',
    'unknown_overhead': 'unlocated_residual',
}


__all__ = ['REQUEST_BUCKET_CATEGORY_MAP']
