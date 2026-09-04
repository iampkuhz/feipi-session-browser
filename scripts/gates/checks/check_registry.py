"""检查并登记 Check ID 与实现模块之间的唯一映射，用于防止重复或游离 owner。

每个 ID 只对应一个领域模块，唯一公开入口固定为模块中的 ``check`` 函数。本模块不负责执行
检查；失败表示映射重复、入口缺失或没有逻辑 Gate recipe 拥有该 Check。"""

from __future__ import annotations

from scripts.gates.checks.check_protocol import CheckSpec

_ROWS = (
    ('agent.entrypoints', 'scripts.gates.checks.agent.check_entrypoints'),
    ('agent.documentation', 'scripts.gates.checks.agent.check_documentation'),
    ('agent.skill-registry', 'scripts.gates.checks.agent.check_skill_registry'),
    (
        'repository.acceptance-traceability',
        'scripts.gates.checks.repository.check_acceptance_traceability',
    ),
    (
        'repository.current-version',
        'scripts.gates.checks.repository.check_current_version',
    ),
    (
        'repository.maintenance-language',
        'scripts.gates.checks.repository.check_maintenance_language',
    ),
    (
        'repository.test-skip-prohibition',
        'scripts.gates.checks.repository.check_test_skip_prohibition',
    ),
    (
        'repository.python-dependency-audit',
        'scripts.gates.checks.repository.check_python_dependency_audit',
    ),
    (
        'repository.file-boundary',
        'scripts.gates.checks.repository.check_file_boundary',
    ),
    (
        'repository.test-data-privacy',
        'scripts.gates.checks.repository.check_test_data_privacy',
    ),
    ('privacy.credential-leak', 'scripts.gates.checks.privacy.check_credential_leak'),
    ('source.code-comment-language', 'scripts.gates.checks.source.check_code_comment_language'),
)

CHECKS = {check_id: CheckSpec(check_id, module) for check_id, module in _ROWS}


def get_check(check_id: str) -> CheckSpec:
    """返回已注册 check；未知 ID fail-closed。"""
    try:
        return CHECKS[check_id]
    except KeyError as exc:
        raise ValueError(f'unknown check id: {check_id}') from exc
