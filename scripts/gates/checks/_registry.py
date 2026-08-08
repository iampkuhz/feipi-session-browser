"""登记 check ID 与实现模块之间的唯一映射。

每个 ID 只对应一个 `check_*.py` 模块，每个模块也只登记一次，并且必须由一个逻辑 Gate recipe
拥有；具体入口固定为模块中的 `check` 函数，因此这里不再保存可变函数名，也不负责执行检查。
"""

from __future__ import annotations

from scripts.gates.checks._framework import CheckSpec

_ROWS = (
    ('agent.runtime-policy', 'scripts.gates.checks.agent.check_agent_runtime_policy'),
    ('agent.document-policy', 'scripts.gates.checks.agent.check_agent_document_policy'),
    ('agent.skill-registry', 'scripts.gates.checks.agent.check_skill_registry'),
    (
        'repository.acceptance-case-mapping',
        'scripts.gates.checks.repository.check_acceptance_case_mapping',
    ),
    (
        'repository.current-source-policy',
        'scripts.gates.checks.repository.check_current_source_policy',
    ),
    ('repository.language-policy', 'scripts.gates.checks.source.check_language_policy'),
    (
        'repository.no-python-playwright-skips',
        'scripts.gates.checks.repository.check_no_python_playwright_skips',
    ),
    (
        'repository.python-dependency-vulnerabilities',
        'scripts.gates.checks.repository.check_python_dependency_vulnerabilities',
    ),
    (
        'repository.repository-file-policy',
        'scripts.gates.checks.repository.check_repository_file_policy',
    ),
    (
        'repository.test-data-policy',
        'scripts.gates.checks.repository.check_test_data_policy',
    ),
    ('security.secret-like-content', 'scripts.gates.checks.privacy.check_secret_like_content'),
    ('source.comment-language', 'scripts.gates.checks.source.check_code_comment_language'),
)

CHECKS = {check_id: CheckSpec(check_id, module) for check_id, module in _ROWS}


def get_check(check_id: str) -> CheckSpec:
    """返回已注册 check；未知 ID fail-closed。"""
    try:
        return CHECKS[check_id]
    except KeyError as exc:
        raise ValueError(f'unknown check id: {check_id}') from exc
