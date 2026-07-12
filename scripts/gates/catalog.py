"""维护 repository 唯一 typed Gate catalog，不承载执行流程。

不负责产品业务处理；由 Gate CLI 或 Stop pipeline 调用。"""

from __future__ import annotations

from scripts.gates.model import (
    ChangedFilesInput,
    ExecutorType,
    GateCatalog,
    GateSpec,
    GateTargetRule,
    IncrementalMode,
    PathRule,
    ReceiptPolicy,
    TargetSpec,
    TierSpec,
)

CATALOG_VERSION = 'gate-catalog:v3'

# target、Gate 顺序与增量 pattern 在同一 registration 中声明，禁止另建映射副本。
_TARGET_REGISTRATIONS = (
    (
        'python-standard',
        (
            ('pythonFormat', ('pyproject.toml', 'scripts/**/*.py', 'tests/**/*.py')),
            ('pythonLint', ('pyproject.toml', 'scripts/**/*.py', 'tests/**/*.py')),
            ('pythonType', ('pyproject.toml', 'scripts/**/*.py', 'tests/**/*.py')),
            ('pythonDocstring', ('pyproject.toml', 'scripts/**/*.py')),
            ('pythonCoverage', ('pyproject.toml', 'tests/**/*.py')),
            (
                'pythonAudit',
                (
                    'pyproject.toml',
                    'requirements*.txt',
                    'requirements*.lock',
                    'uv.lock',
                    'scripts/**/*.py',
                ),
            ),
            ('pythonComplexity', ('pyproject.toml', 'scripts/**/*.py')),
            ('pythonDeadCode', ('pyproject.toml', 'scripts/**/*.py', 'tests/**/*.py')),
            (
                'pythonDeps',
                ('pyproject.toml', 'requirements*.txt', 'requirements*.lock', 'uv.lock'),
            ),
        ),
    ),
    (
        'hook-runtime',
        (
            (
                'ignoredTrackedFiles',
                (
                    '.gitignore',
                    'scripts/checks/check_ignored_tracked_files.py',
                    'scripts/gates/**',
                ),
            ),
            (
                'settingsJson',
                (
                    '.claude/settings.json',
                    '.claude/settings.local.json',
                    '.codex/hooks.json',
                    '.qoder/settings.json',
                    '.qoder/settings.local.example.json',
                ),
            ),
            (
                'bashSyntax',
                (
                    '.claude/hooks/**/*.sh',
                    '.codex/hooks/**/*.sh',
                    '.qoder/hooks/**/*.sh',
                    'scripts/hooks/**/*.sh',
                    'scripts/agent_runtime/**/*.sh',
                    'scripts/harness/**/*.sh',
                ),
            ),
            (
                'scriptCommentLanguage',
                (
                    '.claude/hooks/**/*.sh',
                    '.codex/hooks/**/*.sh',
                    '.qoder/hooks/**/*.sh',
                    'scripts/**/*.py',
                    'scripts/**/*.sh',
                    'java/web/src/main/resources/static/**/*.js',
                    'java/web/src/main/resources/static/**/*.css',
                    'java/web/src/main/resources/templates/**/*.html',
                ),
            ),
            (
                'pythonCompile',
                (
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'noTestSkips',
                (
                    'tests/**/*.py',
                    'tests/**/*.js',
                    'tests/**/*.ts',
                    'playwright.config.js',
                    'scripts/checks/check_no_test_skips.py',
                ),
            ),
            (
                'languagePolicy',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    'skills/**',
                    '.agents/skills/**',
                    '.codex/**',
                    '.claude/agents/**',
                    '.claude/skills/**',
                    '.qoder/**',
                    'harness/**',
                    'openspec/changes/**',
                    'scripts/checks/check_language_policy.py',
                ),
            ),
            (
                'codexAgentPolicy',
                ('.codex/agents/**', 'scripts/checks/check_codex_agent_policy.py'),
            ),
            (
                'agentHookParity',
                (
                    'harness/agent-runtime.manifest.yaml',
                    '.codex/hooks.json',
                    '.qoder/settings.json',
                    '.qoder/settings.local.example.json',
                    '.codex/hooks/**/*.sh',
                    '.qoder/hooks/**/*.sh',
                    'scripts/checks/check_agent_hook_parity.py',
                ),
            ),
            (
                'agentRuntimeIsolation',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'agentRuntimeWorktree',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'gateBypassResistance',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'gateEscapeRate',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'protectedRootsSync',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'qoderRuntimeParity',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'hookPayloadCompat',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'subagentHandoffProtocol',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            ('hookSelfTest', ('scripts/agent_runtime/**/*.py',)),
            (
                'pytest',
                (
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'doctor',
                (
                    '.claude/hooks/**/*.sh',
                    '.codex/hooks/**/*.sh',
                    '.qoder/hooks/**/*.sh',
                    '.claude/settings.json',
                    'scripts/**/*.sh',
                    'pyproject.toml',
                    'requirements*.txt',
                    'requirements*.lock',
                    'uv.lock',
                    '.pre-commit-config.yaml',
                    '.github/workflows/**',
                ),
            ),
            (
                'repoStructure',
                (
                    '.claude/**',
                    '.codex/**',
                    '.github/workflows/**',
                    '.pre-commit-config.yaml',
                    'skills/**',
                    '.agents/skills/**',
                    '.qoder/**',
                    'scripts/**/*.py',
                    'scripts/**/*.sh',
                    'AGENTS.md',
                    'CLAUDE.md',
                    'README.md',
                    'pyproject.toml',
                    'requirements*.txt',
                    'requirements*.lock',
                    'uv.lock',
                    'docs/**',
                ),
            ),
            (
                'repoSlimming',
                (
                    'java/web/src/main/resources/static/**/*.css',
                    'java/web/src/main/resources/static/**/*.js',
                    'java/web/src/main/resources/static/css/**/*.css',
                    'harness/**',
                    'openspec/**',
                    'tests/**/*.py',
                    'scripts/checks/repo_slimming_contract_check.py',
                    'tests/quality/test_repo_slimming_contract.py',
                ),
            ),
            (
                'rawInnerhtml',
                (
                    'java/web/src/main/resources/static/**/*.js',
                    'scripts/checks/check_raw_innerhtml.py',
                ),
            ),
            (
                'layoutInlineStyle',
                (
                    'java/web/src/main/resources/static/**/*.js',
                    'scripts/checks/check_layout_inline_style.py',
                ),
            ),
            (
                'acceptanceContracts',
                (
                    'scripts/checks/validate_acceptance_contracts.py',
                    'tests/quality/test_contract_case_specs.py',
                ),
            ),
        ),
    ),
    (
        'harness',
        (
            ('bashSyntax', ('scripts/harness/**/*.sh',)),
            (
                'scriptCommentLanguage',
                (
                    '.claude/hooks/**/*.sh',
                    '.codex/hooks/**/*.sh',
                    '.qoder/hooks/**/*.sh',
                    'scripts/**/*.py',
                    'scripts/**/*.sh',
                    'java/web/src/main/resources/static/**/*.js',
                    'java/web/src/main/resources/static/**/*.css',
                    'java/web/src/main/resources/templates/**/*.html',
                ),
            ),
            (
                'pythonCompile',
                ('scripts/harness/**/*.py', 'scripts/checks/**/*.py', 'scripts/gates/**/*.py'),
            ),
            (
                'noTestSkips',
                (
                    'tests/**/*.py',
                    'tests/**/*.js',
                    'tests/**/*.ts',
                    'playwright.config.js',
                    'scripts/checks/check_no_test_skips.py',
                ),
            ),
            (
                'languagePolicy',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    'skills/**',
                    '.agents/skills/**',
                    '.codex/**',
                    '.claude/agents/**',
                    '.claude/skills/**',
                    '.qoder/**',
                    'harness/**',
                    'openspec/changes/**',
                    'scripts/checks/check_language_policy.py',
                ),
            ),
            (
                'codexAgentPolicy',
                ('.codex/agents/**', 'scripts/checks/check_codex_agent_policy.py'),
            ),
            (
                'agentRuntimeManifest',
                (
                    'harness/agent-runtime.manifest.yaml',
                    'scripts/checks/check_agent_runtime_manifest.py',
                ),
            ),
            (
                'agentHookParity',
                (
                    'harness/agent-runtime.manifest.yaml',
                    '.codex/hooks.json',
                    '.qoder/settings.json',
                    '.qoder/settings.local.example.json',
                    '.codex/hooks/pre_write_guard.sh',
                    '.qoder/hooks/pre_write_guard.sh',
                    'scripts/checks/check_agent_hook_parity.py',
                ),
            ),
            (
                'agentRuntimeIsolation',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'agentRuntimeWorktree',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'gateBypassResistance',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'gateEscapeRate',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'protectedRootsSync',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'qoderRuntimeParity',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'hookPayloadCompat',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'subagentHandoffProtocol',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.agents/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    'skills/**',
                    'harness/**',
                    'scripts/agent_runtime/**/*.py',
                    'scripts/hooks/**/*.py',
                    'scripts/harness/**/*.py',
                    'scripts/harness/**/*.sh',
                    'scripts/checks/**/*.py',
                    'scripts/gates/**/*.py',
                ),
            ),
            (
                'agentPolicySize',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.codex/config.toml',
                    'harness/agent-policy.manifest.yaml',
                    'scripts/checks/check_agent_policy_size.py',
                ),
            ),
            (
                'agentRulesSync',
                (
                    'AGENTS.md',
                    'CLAUDE.md',
                    '.codex/model-instructions.md',
                    'harness/agent-policy.manifest.yaml',
                    'harness/agent-runtime.manifest.yaml',
                    'scripts/checks/check_agent_rules_sync.py',
                ),
            ),
            (
                'skillRegistry',
                (
                    'harness/skill-registry.yaml',
                    'skills/**',
                    '.agents/skills/**',
                    '.claude/skills/**',
                    '.codex/skills/**',
                    'scripts/checks/check_skill_registry.py',
                ),
            ),
            (
                'agentEntryParity',
                (
                    '.claude/agents/**',
                    '.codex/agents/**',
                    'skills/**',
                    'scripts/checks/check_agent_entry_parity.py',
                ),
            ),
            (
                'noRealSessionFixtures',
                (
                    'tests/**',
                    'docs/**',
                    'java/**',
                    'scripts/checks/check_no_real_session_fixtures.py',
                ),
            ),
            (
                'secretLikeContent',
                (
                    'tests/**',
                    'docs/**',
                    'java/**',
                    '.claude/**',
                    '.codex/**',
                    '.qoder/**',
                    '.agents/**',
                    'skills/**',
                    'harness/**',
                    'scripts/**',
                    'scripts/checks/check_secret_like_content.py',
                ),
            ),
            (
                'runtimeReport',
                (
                    'harness/agent-runtime.manifest.yaml',
                    'harness/agent-runtime-report.schema.json',
                    'harness/reports/**',
                    'scripts/harness/write_agent_runtime_report.py',
                    'scripts/checks/check_agent_runtime_report.py',
                ),
            ),
            ('doctor', ('scripts/harness/**/*.sh',)),
            ('repoStructure', ('scripts/harness/**',)),
            ('harnessStructure', ('harness/**', 'scripts/harness/**/*.py')),
            ('openspecLayout', ('openspec/**',)),
            (
                'pytest',
                (
                    'scripts/harness/**/*.py',
                    'scripts/agent_runtime/events/evidence.py',
                    'scripts/gates/cli.py',
                    'tests/harness/**/*.py',
                    'tests/gates/test_service_contract.py',
                ),
            ),
        ),
    ),
    (
        'acceptance-contracts',
        (
            (
                'noTestSkips',
                (
                    'tests/**/*.py',
                    'tests/**/*.js',
                    'tests/**/*.ts',
                    'playwright.config.js',
                    'scripts/checks/check_no_test_skips.py',
                ),
            ),
            (
                'acceptanceContracts',
                (
                    'docs/acceptance-contracts/**/*.md',
                    'tests/**/*.py',
                    'tests/**/*.js',
                    'tests/**/*.ts',
                    'scripts/checks/validate_acceptance_contracts.py',
                    'tests/quality/test_contract_case_specs.py',
                    'pyproject.toml',
                ),
            ),
            (
                'pytest',
                (
                    'docs/acceptance-contracts/**/*.md',
                    'tests/**/*.py',
                    'tests/**/*.js',
                    'tests/**/*.ts',
                    'scripts/checks/validate_acceptance_contracts.py',
                    'tests/quality/test_contract_case_specs.py',
                    'pyproject.toml',
                ),
            ),
        ),
    ),
    (
        'session-detail',
        (
            (
                'pythonCompile',
                (
                    'scripts/checks/check_session_detail_*.py',
                    'scripts/checks/run_session_detail_*.py',
                ),
            ),
            (
                'noTestSkips',
                (
                    'tests/**/*.py',
                    'tests/**/*.js',
                    'tests/**/*.ts',
                    'playwright.config.js',
                    'scripts/checks/check_no_test_skips.py',
                ),
            ),
            (
                'scriptCommentLanguage',
                (
                    'java/web/src/main/resources/static/**/*.js',
                    'java/web/src/main/resources/static/**/*.css',
                    'java/web/src/main/resources/templates/**/*.html',
                    'scripts/checks/check_code_comment_language.py',
                    'config/technical-terms.json',
                ),
            ),
            (
                'templateContract',
                (
                    'java/web/src/main/resources/templates/**',
                    'tests/ui/test_web_template_contract.py',
                    'scripts/checks/template_contract_check.py',
                ),
            ),
            (
                'staticCssContract',
                (
                    'java/web/src/main/resources/static/css/**/*.css',
                    'tests/ui/test_web_static_contract.py',
                    'scripts/checks/static_contract_check.py',
                ),
            ),
            (
                'cssOwnership',
                (
                    'java/web/src/main/resources/static/css/**/*.css',
                    'scripts/checks/check_css_ownership.py',
                ),
            ),
            (
                'rawInnerhtml',
                (
                    'java/web/src/main/resources/static/**/*.js',
                    'scripts/checks/check_raw_innerhtml.py',
                ),
            ),
            (
                'layoutInlineStyle',
                (
                    'java/web/src/main/resources/static/**/*.js',
                    'scripts/checks/check_layout_inline_style.py',
                ),
            ),
            (
                'pytest',
                (
                    'java/web/src/main/resources/templates/**',
                    'java/web/src/main/resources/static/**',
                    'tests/ui/**/*.py',
                ),
            ),
            (
                'browserLayout',
                (
                    'java/web/src/main/resources/templates/**',
                    'java/web/src/main/resources/static/**',
                    'tests/playwright/**/*.js',
                    'playwright.config.js',
                ),
            ),
            (
                'browserInteraction',
                (
                    'java/web/src/main/resources/templates/**',
                    'java/web/src/main/resources/static/**',
                    'tests/playwright/**/*.js',
                    'playwright.config.js',
                ),
            ),
        ),
    ),
    ('index', (('indexIntegrity', ('scripts/checks/check_index_integrity.py',)),)),
    (
        'java-src',
        (
            (
                'javaCheck',
                ('java/**/src/main/java/**/*.java', 'java/**/src/test/java/**/*.java', '**/*.java'),
            ),
            (
                'javaModuleBoundaries',
                (
                    'config/architecture/java-modules.yaml',
                    'settings.gradle.kts',
                    'java/**/build.gradle.kts',
                    'java/**/src/main/java/**/*.java',
                    '**/*.java',
                ),
            ),
            (
                'javaChineseComments',
                ('java/**/src/main/java/**/*.java', 'java/**/src/test/java/**/*.java', '**/*.java'),
            ),
            ('javaRecordComponentJavadocs', ('java/**/src/main/java/**/*.java', '**/*.java')),
            ('noJavaTestSkips', ('java/**/src/test/java/**/*.java',)),
            ('noJavaSuppressWarnings', ('java/**/src/main/java/**/*.java',)),
            ('reuseStandardCpd', ('java/**/src/main/java/**/*.java', 'config/reuse-policy/**')),
            ('reuseAnalyzeIncremental', ('java/**/src/main/java/**/*.java',)),
            (
                'javaApiSnapshot',
                ('config/api-snapshots/java-public-api.txt', 'java/**/src/main/java/**/*.java'),
            ),
        ),
    ),
    (
        'java-build',
        (
            (
                'javaCheck',
                (
                    'config/api-snapshots/java-public-api.txt',
                    'config/architecture/java-modules.yaml',
                    'build-logic/**',
                    'gradle/**',
                    'build.gradle.kts',
                    'settings.gradle.kts',
                    'java/**/build.gradle.kts',
                    'gradle.properties',
                    'gradlew',
                    'gradlew.bat',
                    '*.lockfile',
                ),
            ),
            (
                'javaModuleBoundaries',
                (
                    'config/architecture/java-modules.yaml',
                    'settings.gradle.kts',
                    'java/**/build.gradle.kts',
                ),
            ),
            (
                'reuseStandardCpd',
                (
                    'config/reuse-policy/**',
                    'java/**/build.gradle.kts',
                    'settings.gradle.kts',
                    'build.gradle.kts',
                ),
            ),
            (
                'reuseAnalyzeIncremental',
                (
                    'config/reuse-policy/**',
                    'java/**/build.gradle.kts',
                    'settings.gradle.kts',
                    'build.gradle.kts',
                ),
            ),
            ('javaApiSnapshot', ('config/api-snapshots/java-public-api.txt',)),
        ),
    ),
    (
        'scan-script-smoke',
        (
            (
                'scanScriptSmoke',
                (
                    'scripts/session-browser.sh',
                    'java/app-cli/**',
                    'java/scan-engine/**',
                    'java/sources/**',
                    'java/index-sqlite/**',
                    'scripts/checks/**',
                    'tests/script_commands/**',
                ),
            ),
            (
                'sessionSamples',
                (
                    'docs/session-samples/**',
                    'java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**',
                    'java/sources/**',
                    'java/normalization-engine/**',
                    'java/artifact-normalized/**',
                    'java/tests/contracts/src/test/java/com/feipi/session/browser/contracttest/sample/**',
                ),
            ),
        ),
    ),
)

# target dominance/并发元数据是 catalog registration 的组成部分。
_TARGET_ROWS = (
    ('python-standard', (), True, (), 300),
    ('hook-runtime', (), True, (), 300),
    ('harness', (), True, (), 120),
    ('acceptance-contracts', (), True, (), 120),
    ('session-detail', (), True, ('fixture-server', 'playwright-browser'), 300),
    ('index', (), True, (), 120),
    ('java-src', ('java-build',), True, ('gradle-daemon', 'java-build-tree'), 1200),
    ('java-build', (), True, ('gradle-daemon', 'java-build-tree'), 300),
    ('scan-script-smoke', (), True, ('gradle-daemon', 'java-build-tree'), 300),
)

# Gate 资源按真实执行能力声明，不能把 target 的浏览器资源机械传播给共享 pytest。
_GATE_RESOURCE_OVERRIDES = {
    'browserLayout': ('fixture-server', 'playwright-browser'),
    'browserInteraction': ('fixture-server', 'playwright-browser'),
    'javaCheck': ('gradle-daemon', 'java-build-tree'),
    'javaModuleBoundaries': ('gradle-daemon', 'java-build-tree'),
    'javaChineseComments': ('gradle-daemon', 'java-build-tree'),
    'javaRecordComponentJavadocs': ('gradle-daemon', 'java-build-tree'),
    'noJavaTestSkips': ('gradle-daemon', 'java-build-tree'),
    'noJavaSuppressWarnings': ('gradle-daemon', 'java-build-tree'),
    'reuseStandardCpd': ('gradle-daemon', 'java-build-tree'),
    'reuseAnalyzeIncremental': ('gradle-daemon', 'java-build-tree'),
    'javaApiSnapshot': ('gradle-daemon', 'java-build-tree'),
    'scanScriptSmoke': ('gradle-daemon', 'java-build-tree'),
    'sessionSamples': ('gradle-daemon', 'java-build-tree'),
}

# changed path 分类按顺序首个命中；unknown Java/Gradle fail-closed 规则位于末尾。
_PATH_ROWS = (
    (
        'acceptance-contract',
        ('docs/acceptance-contracts/**',),
        True,
        'acceptance-contracts',
        'medium',
        True,
    ),
    (
        'java-src',
        ('java/**/src/main/java/**/*.java', 'java/**/src/test/java/**/*.java'),
        True,
        'java-src',
        'medium',
        True,
    ),
    (
        'java-build',
        (
            'build-logic/**',
            'gradle/**',
            'config/api-snapshots/java-public-api.txt',
            'config/architecture/java-modules.yaml',
            'config/pmd/**',
            'config/reuse-policy/**',
            'settings.gradle.kts',
            'java/**/build.gradle.kts',
            'gradlew',
            'gradlew.bat',
            '*.lockfile',
        ),
        True,
        'java-build',
        'medium',
        True,
    ),
    (
        'java-root-dsl',
        ('build.gradle.kts', 'gradle.properties'),
        True,
        'java-build',
        'medium',
        True,
    ),
    (
        'test',
        (
            'tests/**/*.py',
            'tests/*.py',
            'tests/**/*.js',
            'tests/*.js',
            'tests/**/*.ts',
            'tests/*.ts',
        ),
        True,
        'acceptance-contracts',
        'medium',
        True,
    ),
    (
        'session-detail-ui',
        (
            'java/web/src/main/resources/static/**',
            'java/web/src/main/resources/templates/**',
            'src/session_browser/web/**',
            'scripts/checks/check_session_detail_*.py',
            'scripts/checks/run_session_detail_*.py',
        ),
        True,
        'session-detail',
        'medium',
        True,
    ),
    (
        'hook',
        (
            '.claude/hooks/**',
            '.codex/hooks/**',
            '.qoder/hooks/**',
            'scripts/agent_runtime/**',
            'scripts/hooks/**',
        ),
        True,
        'hook-runtime',
        'high',
        True,
    ),
    (
        'quality-gate',
        ('scripts/checks/**', 'scripts/gates/**'),
        True,
        'hook-runtime',
        'high',
        True,
    ),
    ('harness', ('harness/**', 'scripts/harness/**'), True, 'harness', 'high', True),
    ('openspec', ('openspec/**',), True, 'harness', 'medium', True),
    ('repo-script', ('scripts/*.sh', 'scripts/**/*.sh'), True, 'hook-runtime', 'high', True),
    (
        'python-tooling-config',
        (
            'pyproject.toml',
            'requirements*.txt',
            'requirements*.lock',
            'uv.lock',
            '.pre-commit-config.yaml',
            '.github/workflows/**',
        ),
        True,
        'hook-runtime',
        'high',
        True,
    ),
    (
        'agent-config',
        (
            'AGENTS.md',
            'CLAUDE.md',
            'skills/**',
            '.agents/skills/**',
            '.claude/settings.json',
            '.claude/agents/**',
            '.claude/commands/**',
            '.claude/skills/**',
            '.codex/**',
            '.qoder/**',
        ),
        True,
        'hook-runtime',
        'high',
        True,
    ),
    ('docs', ('README.md', 'docs/**'), False, None, 'low', True),
    (
        'local-or-generated',
        (
            'tmp/**',
            'data/**',
            'output/**',
            '.venv/**',
            '.pytest_cache/**',
            '**/*.sqlite',
            '**/*.sqlite3',
            '**/*.db',
        ),
        False,
        None,
        'local',
        True,
    ),
    ('java-src-unknown', ('**/*.java',), True, 'java-src', 'high', False),
    ('java-build-unknown', ('**/*.gradle', '**/*.gradle.kts'), True, 'java-build', 'high', False),
)

_SCAN_SCRIPT_SMOKE_PATTERNS = (
    'scripts/session-browser.sh',
    'java/app-cli/**',
    'java/scan-engine/**',
    'java/sources/**',
    'java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**',
    'java/normalization-engine/**',
    'java/artifact-normalized/**',
    'java/index-sqlite/**',
    'docs/session-samples/**',
    'scripts/checks/**',
)

_QUICK_GATE_NAMES = (
    'bashSyntax',
    'pythonCompile',
    'noTestSkips',
    'languagePolicy',
    'agentRuntimeIsolation',
    'agentRuntimeWorktree',
    'gateBypassResistance',
    'gateEscapeRate',
    'protectedRootsSync',
    'qoderRuntimeParity',
    'hookPayloadCompat',
    'subagentHandoffProtocol',
    'doctor',
    'repoStructure',
    'harnessStructure',
    'noJavaTestSkips',
    'noJavaSuppressWarnings',
)

_GRADLE_TASKS = {
    'javaCheck': ('check',),
    'javaRecordComponentJavadocs': (':java:tests:quality-gates:verifyJavaRecordComponentJavadocs',),
    'reuseAnalyzeIncremental': ('reuseAnalyzeIncremental',),
}

# 只有确实读取该环境变量的 Gate 才能获得 changed-files；其余 Gate 只消费 planner 结果。
_CHANGED_FILES_INPUTS = {
    'languagePolicy': ChangedFilesInput.ENVIRONMENT,
    'javaRecordComponentJavadocs': ChangedFilesInput.ENVIRONMENT,
    'reuseStandardCpd': ChangedFilesInput.ENVIRONMENT,
}


# 把紧凑 registration 冻结为 typed target specs。
def _build_targets() -> tuple[TargetSpec, ...]:
    """返回：
    当前函数的稳定结果。
    """
    return tuple(
        TargetSpec(
            name=name,
            includes=includes,
            parallel_safe=parallel_safe,
            exclusive_resources=resources,
            timeout_seconds=timeout,
            description=f'质量目标 {name} 的确定性执行边界。',
        )
        for name, includes, parallel_safe, resources, timeout in _TARGET_ROWS
    )


# 合并 target registrations，生成每个逻辑 Gate 唯一的 typed spec。
def _build_gates(targets: tuple[TargetSpec, ...]) -> tuple[GateSpec, ...]:
    """合并 target registrations，生成每个逻辑 Gate 唯一的 typed spec。"""
    names = tuple(dict.fromkeys(name for _, rows in _TARGET_REGISTRATIONS for name, _ in rows))
    target_index = {target.name: target for target in targets}
    result: list[GateSpec] = []
    for name in names:
        rules = tuple(
            GateTargetRule(target=target, order=order, patterns=patterns)
            for target, rows in _TARGET_REGISTRATIONS
            for order, (gate_name, patterns) in enumerate(rows)
            if gate_name == name
        )
        metadata = tuple(target_index[rule.target] for rule in rules)
        resources = _GATE_RESOURCE_OVERRIDES.get(name, ())
        gradle_tasks = _GRADLE_TASKS.get(name, ())
        result.append(
            GateSpec(
                name=name,
                target_rules=rules,
                executor_type=ExecutorType.GRADLE if gradle_tasks else ExecutorType.COMMAND,
                command_key=None if gradle_tasks else name,
                gradle_tasks=gradle_tasks,
                timeout_seconds=max(target.timeout_seconds for target in metadata),
                parallel_safe=all(target.parallel_safe for target in metadata),
                exclusive_resources=resources,
                incremental_mode=(
                    IncrementalMode.PATTERNS
                    if any(rule.patterns for rule in rules)
                    else IncrementalMode.ALWAYS
                ),
                changed_files_input=_CHANGED_FILES_INPUTS.get(name, ChangedFilesInput.NONE),
                included_by=(),
                tiers=(
                    ('full',)
                    if name == 'javaApiSnapshot'
                    else (
                        ('quick', 'required', 'full')
                        if name in _QUICK_GATE_NAMES
                        else ('required', 'full')
                    )
                ),
                receipt_policy=ReceiptPolicy.CONTENT_SENSITIVE,
                description=f'执行 {name} 所定义的仓库质量检查。',
            )
        )
    return tuple(result)


_TARGET_SPECS = _build_targets()
_GATE_SPECS = _build_gates(_TARGET_SPECS)
_PATH_RULES = tuple(
    PathRule(
        category=category,
        patterns=patterns,
        requires_quality_gate=required,
        quality_target=target,
        risk_level=risk,
        allowed_by_default=allowed,
    )
    for category, patterns, required, target, risk, allowed in _PATH_ROWS
)
_TIER_SPECS = (
    TierSpec(
        name='quick',
        description='本地开发默认快速反馈，只运行轻量级 Gate 子集。',
        failure_policy='triggered Gate 必须 PASS；not triggered 不算 skipped。',
        gate_names=_QUICK_GATE_NAMES,
    ),
    TierSpec(
        name='required',
        description='PR 合入和 Stop/handoff 前必须通过。',
        failure_policy='0 skipped outcome；skipped 即 FAIL/BLOCKED。',
        gate_names=None,
    ),
    TierSpec(
        name='full',
        description='发布或大迁移收口前运行，包含全部 target 和额外验证。',
        failure_policy='0 skipped outcome；skipped 即 FAIL/BLOCKED。',
        gate_names=None,
    ),
)

CATALOG = GateCatalog(
    version=CATALOG_VERSION,
    gates=_GATE_SPECS,
    targets=_TARGET_SPECS,
    path_rules=_PATH_RULES,
    scan_script_smoke_patterns=_SCAN_SCRIPT_SMOKE_PATTERNS,
    tiers=_TIER_SPECS,
)
GATES: tuple[GateSpec, ...] = CATALOG.gates
TARGETS: tuple[TargetSpec, ...] = CATALOG.targets
TIERS: tuple[TierSpec, ...] = CATALOG.tiers


# 返回已注册 Gate；未知名称立即失败，避免 executor 静默放行。
def gate_by_name(name: str) -> GateSpec:
    """返回已注册 Gate；未知名称立即失败，避免 executor 静默放行。"""
    for gate in GATES:
        if gate.name == name:
            return gate
    raise ValueError(f'Unknown quality gate: {name}')


# 返回已注册 target；未知名称立即失败。
def target_by_name(name: str) -> TargetSpec:
    """返回已注册 target；未知名称立即失败。"""
    for target in TARGETS:
        if target.name == name:
            return target
    raise ValueError(f'Unknown quality target: {name}')


# 返回已注册 tier；未知名称立即失败。
def tier_by_name(name: str) -> TierSpec:
    """返回已注册 tier；未知名称立即失败。"""
    for tier in TIERS:
        if tier.name == name:
            return tier
    raise ValueError(f'Unknown quality tier: {name}')
