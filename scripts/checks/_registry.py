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
    (
        'repository.acceptance-case-mapping',
        'scripts.checks.repository.check_acceptance_case_mapping',
    ),
    ('repository.current-source-policy', 'scripts.checks.repository.check_current_source_policy'),
    ('repository.dead-command-reference', 'scripts.checks.repository.check_dead_command_reference'),
    ('repository.gate-escape-rate', 'scripts.checks.repository.check_gate_escape_rate'),
    ('repository.language-policy', 'scripts.checks.source.check_language_policy'),
    (
        'repository.no-python-playwright-skips',
        'scripts.checks.repository.check_no_python_playwright_skips',
    ),
    (
        'repository.python-dependency-vulnerabilities',
        'scripts.checks.repository.check_python_dependency_vulnerabilities',
    ),
    (
        'repository.repository-file-policy',
        'scripts.checks.repository.check_repository_file_policy',
    ),
    (
        'repository.test-data-policy',
        'scripts.checks.repository.check_test_data_policy',
    ),
    (
        'repository.no-product-python',
        'scripts.checks.source.check_no_new_product_python',
    ),
    ('security.secret-like-content', 'scripts.checks.privacy.check_secret_like_content'),
    ('web.js-action-handlers', 'scripts.checks.web.check_js_action_handlers'),
    ('source.comment-language', 'scripts.checks.source.check_code_comment_language'),
)

CHECKS = {check_id: CheckSpec(check_id, module) for check_id, module in _ROWS}


def get_check(check_id: str) -> CheckSpec:
    """返回已注册 check；未知 ID fail-closed。"""
    try:
        return CHECKS[check_id]
    except KeyError as exc:
        raise ValueError(f'unknown check id: {check_id}') from exc
