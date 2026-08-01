"""登记 check ID 与实现模块之间的唯一映射。

每个 ID 只对应一个 `check_*.py` 模块，每个模块也只登记一次；具体入口固定为模块中的 `check`
函数，因此这里不再保存可变函数名，也不负责执行检查。
"""

from __future__ import annotations

from scripts.checks._framework import CheckSpec

_ROWS = (
    ('agent.entry-parity', 'scripts.checks.agent.check_agent_entry_parity'),
    ('agent.policy-size', 'scripts.checks.agent.check_agent_policy_size'),
    ('agent.permission-policy', 'scripts.checks.agent.check_agent_permission_policy'),
    ('agent.rules-sync', 'scripts.checks.agent.check_agent_rules_sync'),
    ('agent.codex-policy', 'scripts.checks.agent.check_codex_agent_policy'),
    ('agent.protected-roots', 'scripts.checks.agent.check_protected_roots_sync'),
    ('agent.skill-registry', 'scripts.checks.agent.check_skill_registry'),
    ('agent.subagent-handoff', 'scripts.checks.agent.check_subagent_handoff_protocol'),
    ('openspec.acceptance-contracts', 'scripts.checks.repository.check_acceptance_contracts'),
    ('repository.dead-command-reference', 'scripts.checks.repository.check_dead_command_reference'),
    ('repository.gate-escape-rate', 'scripts.checks.repository.check_gate_escape_rate'),
    ('repository.ignored-tracked', 'scripts.checks.repository.check_ignored_tracked_files'),
    ('repository.index-integrity', 'scripts.checks.repository.check_index_integrity'),
    ('repository.language-policy', 'scripts.checks.source.check_language_policy'),
    (
        'repository.misplaced-generated-paths',
        'scripts.checks.repository.check_misplaced_generated_paths',
    ),
    (
        'repository.no-committed-local-paths',
        'scripts.checks.privacy.check_no_committed_local_paths',
    ),
    (
        'repository.no-real-session-fixtures',
        'scripts.checks.privacy.check_no_real_session_fixtures',
    ),
    ('repository.no-test-skips', 'scripts.checks.repository.check_no_test_skips'),
    ('repository.python-security', 'scripts.checks.repository.check_python_security'),
    ('repository.repo-slimming', 'scripts.checks.repository.check_repo_slimming'),
    ('repository.structure', 'scripts.checks.repository.check_repo_structure'),
    (
        'repository.no-product-python',
        'scripts.checks.source.check_no_new_product_python',
    ),
    ('security.secret-like-content', 'scripts.checks.privacy.check_secret_like_content'),
    ('web.css-ownership', 'scripts.checks.web.check_css_ownership'),
    ('web.layout-inline-style', 'scripts.checks.web.check_layout_inline_style'),
    ('web.js-action-handlers', 'scripts.checks.web.check_js_action_handlers'),
    ('web.raw-innerhtml', 'scripts.checks.web.check_raw_innerhtml'),
    ('web.session-detail-static', 'scripts.checks.web.check_session_detail_static'),
    ('web.static-contract', 'scripts.checks.web.check_static_contract'),
    ('source.comment-language', 'scripts.checks.source.check_code_comment_language'),
)

CHECKS = {check_id: CheckSpec(check_id, module) for check_id, module in _ROWS}


def get_check(check_id: str) -> CheckSpec:
    """返回已注册 check；未知 ID fail-closed。"""
    try:
        return CHECKS[check_id]
    except KeyError as exc:
        raise ValueError(f'unknown check id: {check_id}') from exc
