"""负责维护 check ID 到领域函数的唯一 registry；不负责执行检查；由共享 CLI 入口调用。"""

from __future__ import annotations

from scripts.checks._framework import CheckSpec

_ROWS = (
    ('agent.entry-parity', 'check_agent_entry_parity'),
    ('agent.hook-parity', 'check_agent_hook_parity'),
    ('agent.policy-size', 'check_agent_policy_size'),
    ('agent.rules-sync', 'check_agent_rules_sync'),
    ('agent.runtime-isolation', 'check_agent_runtime_isolation'),
    ('agent.runtime-manifest', 'check_agent_runtime_manifest'),
    ('agent.runtime-report', 'check_agent_runtime_report'),
    ('agent.runtime-worktree', 'check_agent_runtime_worktree'),
    ('agent.codex-policy', 'check_codex_agent_policy'),
    ('agent.hook-payload', 'check_hook_payload_compat'),
    ('agent.protected-roots', 'check_protected_roots_sync'),
    ('agent.permission-policy', 'check_agent_permission_policy', 'check_permission_policy'),
    ('agent.qoder-parity', 'check_qoder_runtime_parity', 'main'),
    ('agent.skill-registry', 'check_skill_registry'),
    ('agent.subagent-handoff', 'check_subagent_handoff_protocol'),
    ('openspec.acceptance-contracts', 'validate_acceptance_contracts'),
    ('repository.dead-command-reference', 'check_dead_command_reference'),
    ('repository.gate-bypass', 'measure_gate_escape_rate', 'main'),
    ('repository.gate-escape-rate', 'measure_gate_escape_rate'),
    ('repository.ignored-tracked', 'check_ignored_tracked_files'),
    ('repository.index-integrity', 'check_index_integrity'),
    ('repository.language-policy', 'check_language_policy'),
    ('repository.no-committed-local-paths', 'check_no_committed_local_paths', 'check_local_paths'),
    ('repository.no-real-session-fixtures', 'check_no_real_session_fixtures'),
    ('repository.no-test-skips', 'check_no_test_skips'),
    ('repository.repo-slimming', 'repo_slimming_contract_check'),
    ('repository.structure', 'validate_repo_structure'),
    ('repository.no-product-python', 'check_no_new_product_python', 'check_product_python'),
    ('security.secret-like-content', 'check_secret_like_content'),
    ('web.css-ownership', 'check_css_ownership'),
    ('web.layout-inline-style', 'check_layout_inline_style'),
    ('web.js-action-handlers', 'check_js_action_handlers', 'check_action_handlers'),
    ('web.raw-innerhtml', 'check_raw_innerhtml'),
    ('web.session-detail-static', 'check_session_detail_static', 'check_repository'),
    ('web.static-contract', 'static_contract_check'),
    ('web.template-contract', 'template_contract_check'),
    ('source.comment-language', 'check_code_comment_language'),
    ('java.api-snapshot', 'check_java_api_snapshot'),
    ('java.no-test-skips', 'check_no_java_test_skips'),
    ('java.no-suppress-warnings', 'check_no_java_suppress_warnings'),
)

CHECKS = {
    row[0]: CheckSpec(row[0], f'scripts.checks.{row[1]}', row[2] if len(row) == 3 else 'main')
    for row in _ROWS
}


def get_check(check_id: str) -> CheckSpec:
    """返回已注册 check；未知 ID fail-closed。"""
    try:
        return CHECKS[check_id]
    except KeyError as exc:
        raise ValueError(f'unknown check id: {check_id}') from exc
