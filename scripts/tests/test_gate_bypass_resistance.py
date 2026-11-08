"""验证高风险路径选择现有 Gate，不运行 owner。"""

from scripts.gates.planning import ChangeSnapshot, compile_gate_plan

EXPECTED_PATH_GATES = (
    ('.claude/agents/qwen-main-default.md', 'agentConfigurationPolicy'),
    ('.claude/agents/qwen-main-default.md', 'credentialLeakScan'),
    ('skills/authoring/feipi-java-feature-dev/SKILL.md', 'governanceLayoutValidation'),
    ('docs/acceptance-cases/features/HOOK_HARNESS.md', 'acceptanceTraceability'),
    ('scripts/gates/planning/plan_compiler.py', 'gateFrameworkTests'),
    ('java/web/src/main/java/com/feipi/session/browser/X.java', 'javaBuildVerification'),
    ('java/build.gradle.kts', 'javaBuildVerification'),
    ('java/web/src/main/resources/templates/session-detail.html', 'browserTests'),
    ('.qoder/settings.json', 'agentConfigurationPolicy'),
    ('scripts/session-browser.sh', 'scanCommandSmoke'),
    ('.agents/experimental/new-policy.yaml', 'agentConfigurationPolicy'),
    ('java/index-store-sqlite/src/main/resources/sql/schema.sql', 'javaBuildVerification'),
    ('README.md', 'repositoryBoundaryAudit'),
)


def test_high_risk_paths_select_their_required_gate() -> None:
    for path, expected in EXPECTED_PATH_GATES:
        snapshot = ChangeSnapshot('git-working-tree', 'head', None, (path,), 'fingerprint')
        selected = {gate.name for gate in compile_gate_plan(snapshot).gates}
        assert expected in selected, (path, selected)
