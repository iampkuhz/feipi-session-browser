"""提供 quality targets 脚本能力。"""

from __future__ import annotations

import re

# 01. 质量目标到必需门禁的全量基线矩阵。
QUALITY_TARGETS: dict[str, list[str]] = {
    'python-standard': [
        'pythonFormat',
        'pythonLint',
        'pythonType',
        'pythonDocstring',
        'pythonCoverage',
        'pythonAudit',
        'pythonComplexity',
        'pythonDeadCode',
        'pythonDeps',
    ],
    'hook-runtime': [
        'ignoredTrackedFiles',
        'settingsJson',
        'bashSyntax',
        'scriptCommentLanguage',
        'pythonCompile',
        'noTestSkips',
        'languagePolicy',
        'codexAgentPolicy',
        'agentHookParity',
        'agentRuntimeIsolation',
        'agentRuntimeWorktree',
        'gateBypassResistance',
        'gateEscapeRate',
        'protectedRootsSync',
        'qoderRuntimeParity',
        'hookPayloadCompat',
        'subagentHandoffProtocol',
        'hookSelfTest',
        'pytest',
        'doctor',
        'repoStructure',
        'repoSlimming',
        'rawInnerhtml',
        'layoutInlineStyle',
        'acceptanceContracts',
    ],
    'harness': [
        'bashSyntax',
        'scriptCommentLanguage',
        'pythonCompile',
        'noTestSkips',
        'languagePolicy',
        'codexAgentPolicy',
        'agentRuntimeManifest',
        'agentHookParity',
        'agentRuntimeIsolation',
        'agentRuntimeWorktree',
        'gateBypassResistance',
        'gateEscapeRate',
        'protectedRootsSync',
        'qoderRuntimeParity',
        'hookPayloadCompat',
        'subagentHandoffProtocol',
        'agentPolicySize',
        'agentRulesSync',
        'skillRegistry',
        'agentEntryParity',
        'noRealSessionFixtures',
        'secretLikeContent',
        'runtimeReport',
        'doctor',
        'repoStructure',
        'harnessStructure',
        'openspecLayout',
        'pytest',
    ],
    'acceptance-contracts': [
        'noTestSkips',
        'acceptanceContracts',
        'pytest',
    ],
    'session-detail': [
        'pythonCompile',
        'noTestSkips',
        'scriptCommentLanguage',
        'templateContract',
        'staticCssContract',
        'cssOwnership',
        'rawInnerhtml',
        'layoutInlineStyle',
        'pytest',
        'browserLayout',
        'browserInteraction',
    ],
    'index': [
        'indexIntegrity',
    ],
    'java-src': [
        'javaCheck',
        'javaModuleBoundaries',
        'javaChineseComments',
        'javaRecordComponentJavadocs',
        'noJavaTestSkips',
        'noJavaSuppressWarnings',
        'reuseStandardCpd',
        'reuseAnalyzeIncremental',
    ],
    'java-build': [
        'javaCheck',
        'javaModuleBoundaries',
        'reuseStandardCpd',
        'reuseAnalyzeIncremental',
    ],
    'scan-script-smoke': [
        'scanScriptSmoke',
        'sessionSamples',
    ],
}

# 01b. target 并行执行元数据
# parallel_safe: 是否可与其他无冲突 target 并行执行
# exclusive_resources: 互斥资源列表（如 gradle-daemon），同一资源同时只允许一个 target 使用
# timeout: 单 target 最大执行时间（秒）
TARGET_META: dict[str, dict[str, object]] = {
    'python-standard': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300},
    'hook-runtime': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300},
    'harness': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'acceptance-contracts': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'session-detail': {'parallel_safe': True, 'exclusive_resources': ['fixture-server', 'playwright-browser'], 'timeout': 300},
    'index': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'java-src': {'parallel_safe': True, 'exclusive_resources': ['gradle-daemon', 'java-build-tree'], 'timeout': 1200},
    'java-build': {'parallel_safe': True, 'exclusive_resources': ['gradle-daemon', 'java-build-tree'], 'timeout': 300},
    'scan-script-smoke': {'parallel_safe': True, 'exclusive_resources': ['gradle-daemon', 'java-build-tree'], 'timeout': 300},
}

# 01c. target dominance 声明: 当 dominant target 触发时自动包含 dominated target
# java-src 包含 java-build，避免两个 target 各自运行一次 Gradle baseline
TARGET_DOMINANCE: dict[str, dict[str, list[str]]] = {
    'java-src': {'includes': ['java-build']},
}


AGENT_RUNTIME_GATE_PATTERNS: list[str] = [
    'AGENTS.md',
    'CLAUDE.md',
    '.agents/**',
    '.claude/**',
    '.codex/**',
    '.qoder/**',
    'skills/**',
    'harness/**',
    'scripts/claude_hooks/**/*.py',
    'scripts/hooks/**/*.py',
    'scripts/agent_hooks/**/*.py',
    'scripts/harness/**/*.py',
    'scripts/harness/**/*.sh',
    'scripts/quality/**/*.py',
]


# 02. gate 到文件 pattern 映射（incremental trigger）
# 只有 changed file 命中 pattern 时，对应 gate 才会运行。
# 调用方省略 changed files（如手动 --target）时使用 full baseline。
GATE_PATTERNS: dict[str, dict[str, list[str]]] = {
    'python-standard': {
        'pythonFormat': [
            'pyproject.toml',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonLint': [
            'pyproject.toml',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonType': [
            'pyproject.toml',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonDocstring': [
            'pyproject.toml',
            'scripts/**/*.py',
        ],
        'pythonCoverage': [
            'pyproject.toml',
            'tests/**/*.py',
        ],
        'pythonAudit': [
            'pyproject.toml',
            'requirements*.txt',
            'requirements*.lock',
            'uv.lock',
            'scripts/**/*.py',
        ],
        'pythonComplexity': [
            'pyproject.toml',
            'scripts/**/*.py',
        ],
        'pythonDeadCode': [
            'pyproject.toml',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonDeps': [
            'pyproject.toml',
            'requirements*.txt',
            'requirements*.lock',
            'uv.lock',
        ],
    },
    'hook-runtime': {
        'ignoredTrackedFiles': [
            '.gitignore',
            'scripts/quality/check_ignored_tracked_files.py',
            'scripts/quality/run_required_quality_gates.py',
            'scripts/quality/run_quality_gate.py',
        ],
        'settingsJson': [
            '.claude/settings.json',
            '.claude/settings.local.json',
            '.codex/hooks.json',
            '.qoder/settings.json',
            '.qoder/settings.local.example.json',
        ],
        'bashSyntax': [
            '.claude/hooks/**/*.sh',
            '.codex/hooks/**/*.sh',
            '.qoder/hooks/**/*.sh',
            'scripts/hooks/**/*.sh',
            'scripts/agent_hooks/**/*.sh',
            'scripts/harness/**/*.sh',
        ],
        'scriptCommentLanguage': [
            '.claude/hooks/**/*.sh',
            '.codex/hooks/**/*.sh',
            '.qoder/hooks/**/*.sh',
            'scripts/**/*.py',
            'scripts/**/*.sh',
            'java/web/src/main/resources/static/**/*.js',
            'java/web/src/main/resources/static/**/*.css',
            'java/web/src/main/resources/templates/**/*.html',
        ],
        'pythonCompile': [
            'scripts/claude_hooks/**/*.py',
            'scripts/hooks/**/*.py',
            'scripts/agent_hooks/**/*.py',
            'scripts/quality/**/*.py',
        ],
        'noTestSkips': [
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'playwright.config.js',
            'scripts/quality/check_no_test_skips.py',
        ],
        'hookSelfTest': [
            'scripts/claude_hooks/**/*.py',
        ],
        'pytest': [
            'scripts/claude_hooks/**/*.py',
            'scripts/hooks/**/*.py',
            'scripts/agent_hooks/**/*.py',
            'scripts/quality/**/*.py',
        ],
        'doctor': [
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
        ],
        'repoStructure': [
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
        ],
        'repoSlimming': [
            'java/web/src/main/resources/static/**/*.css',
            'java/web/src/main/resources/static/**/*.js',
            'java/web/src/main/resources/static/css/**/*.css',
            'harness/**',
            'openspec/**',
            'tests/**/*.py',
            'scripts/quality/repo_slimming_contract_check.py',
            'tests/quality/test_repo_slimming_contract.py',
        ],
        'rawInnerhtml': [
            'java/web/src/main/resources/static/**/*.js',
            'scripts/quality/check_raw_innerhtml.py',
        ],
        'layoutInlineStyle': [
            'java/web/src/main/resources/static/**/*.js',
            'scripts/quality/check_layout_inline_style.py',
        ],
        'acceptanceContracts': [
            'scripts/quality/validate_acceptance_contracts.py',
            'tests/quality/test_contract_case_specs.py',
        ],
        'languagePolicy': [
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
            'scripts/quality/check_language_policy.py',
        ],
        'codexAgentPolicy': [
            '.codex/agents/**',
            'scripts/quality/check_codex_agent_policy.py',
        ],
        'agentHookParity': [
            'harness/agent-runtime.manifest.yaml',
            '.codex/hooks.json',
            '.qoder/settings.json',
            '.qoder/settings.local.example.json',
            '.codex/hooks/**/*.sh',
            '.qoder/hooks/**/*.sh',
            'scripts/quality/check_agent_hook_parity.py',
        ],
        'agentRuntimeIsolation': AGENT_RUNTIME_GATE_PATTERNS,
        'agentRuntimeWorktree': AGENT_RUNTIME_GATE_PATTERNS,
        'gateBypassResistance': AGENT_RUNTIME_GATE_PATTERNS,
        'gateEscapeRate': AGENT_RUNTIME_GATE_PATTERNS,
        'protectedRootsSync': AGENT_RUNTIME_GATE_PATTERNS,
        'qoderRuntimeParity': AGENT_RUNTIME_GATE_PATTERNS,
        'hookPayloadCompat': AGENT_RUNTIME_GATE_PATTERNS,
        'subagentHandoffProtocol': AGENT_RUNTIME_GATE_PATTERNS,
    },
    'harness': {
        'bashSyntax': [
            'scripts/harness/**/*.sh',
        ],
        'scriptCommentLanguage': [
            '.claude/hooks/**/*.sh',
            '.codex/hooks/**/*.sh',
            '.qoder/hooks/**/*.sh',
            'scripts/**/*.py',
            'scripts/**/*.sh',
            'java/web/src/main/resources/static/**/*.js',
            'java/web/src/main/resources/static/**/*.css',
            'java/web/src/main/resources/templates/**/*.html',
        ],
        'pythonCompile': [
            'scripts/harness/**/*.py',
            'scripts/quality/**/*.py',
        ],
        'noTestSkips': [
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'playwright.config.js',
            'scripts/quality/check_no_test_skips.py',
        ],
        'doctor': [
            'scripts/harness/**/*.sh',
        ],
        'repoStructure': [
            'scripts/harness/**',
        ],
        'harnessStructure': [
            'harness/**',
            'scripts/harness/**/*.py',
        ],
        'openspecLayout': [
            'openspec/**',
        ],
        'pytest': [
            'scripts/harness/**/*.py',
            'scripts/quality/changed_files.py',
            'scripts/quality/run_required_quality_gates.py',
            'tests/harness/**/*.py',
            'tests/quality/test_run_required_quality_gates.py',
        ],
        'languagePolicy': [
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
            'scripts/quality/check_language_policy.py',
        ],
        'agentRuntimeManifest': [
            'harness/agent-runtime.manifest.yaml',
            'scripts/quality/check_agent_runtime_manifest.py',
        ],
        'agentHookParity': [
            'harness/agent-runtime.manifest.yaml',
            '.codex/hooks.json',
            '.qoder/settings.json',
            '.qoder/settings.local.example.json',
            '.codex/hooks/pre_write_guard.sh',
            '.qoder/hooks/pre_write_guard.sh',
            'scripts/quality/check_agent_hook_parity.py',
        ],
        'agentRuntimeIsolation': AGENT_RUNTIME_GATE_PATTERNS,
        'agentRuntimeWorktree': AGENT_RUNTIME_GATE_PATTERNS,
        'gateBypassResistance': AGENT_RUNTIME_GATE_PATTERNS,
        'gateEscapeRate': AGENT_RUNTIME_GATE_PATTERNS,
        'protectedRootsSync': AGENT_RUNTIME_GATE_PATTERNS,
        'qoderRuntimeParity': AGENT_RUNTIME_GATE_PATTERNS,
        'hookPayloadCompat': AGENT_RUNTIME_GATE_PATTERNS,
        'subagentHandoffProtocol': AGENT_RUNTIME_GATE_PATTERNS,
        'codexAgentPolicy': [
            '.codex/agents/**',
            'scripts/quality/check_codex_agent_policy.py',
        ],
        'agentPolicySize': [
            'AGENTS.md',
            'CLAUDE.md',
            '.codex/config.toml',
            'harness/agent-policy.manifest.yaml',
            'scripts/quality/check_agent_policy_size.py',
        ],
        'agentRulesSync': [
            'AGENTS.md',
            'CLAUDE.md',
            '.codex/model-instructions.md',
            'harness/agent-policy.manifest.yaml',
            'harness/agent-runtime.manifest.yaml',
            'scripts/quality/check_agent_rules_sync.py',
        ],
        'skillRegistry': [
            'harness/skill-registry.yaml',
            'skills/**',
            '.agents/skills/**',
            '.claude/skills/**',
            '.codex/skills/**',
            'scripts/quality/check_skill_registry.py',
        ],
        'agentEntryParity': [
            '.claude/agents/**',
            '.codex/agents/**',
            'skills/**',
            'scripts/quality/check_agent_entry_parity.py',
        ],
        'noRealSessionFixtures': [
            'tests/**',
            'docs/**',
            'java/**',
            'app-cli/**',
            'src/**',
            'scripts/quality/check_no_real_session_fixtures.py',
        ],
        'secretLikeContent': [
            'tests/**',
            'docs/**',
            'java/**',
            'app-cli/**',
            'src/**',
            '.claude/**',
            '.codex/**',
            '.qoder/**',
            '.agents/**',
            'skills/**',
            'harness/**',
            'scripts/**',
            'scripts/quality/check_secret_like_content.py',
        ],
        'runtimeReport': [
            'harness/agent-runtime.manifest.yaml',
            'harness/agent-runtime-report.schema.json',
            'harness/reports/**',
            'scripts/harness/write_agent_runtime_report.py',
            'scripts/quality/check_agent_runtime_report.py',
        ],
    },
    'index': {
        'indexIntegrity': [
            'scripts/quality/check_index_integrity.py',
        ],
    },
    'acceptance-contracts': {
        'noTestSkips': [
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'playwright.config.js',
            'scripts/quality/check_no_test_skips.py',
        ],
        'acceptanceContracts': [
            'docs/acceptance-contracts/**/*.md',
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'scripts/quality/validate_acceptance_contracts.py',
            'tests/quality/test_contract_case_specs.py',
            'pyproject.toml',
        ],
        'pytest': [
            'docs/acceptance-contracts/**/*.md',
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'scripts/quality/validate_acceptance_contracts.py',
            'tests/quality/test_contract_case_specs.py',
            'pyproject.toml',
        ],
    },
    'session-detail': {
        'scriptCommentLanguage': [
            'java/web/src/main/resources/static/**/*.js',
            'java/web/src/main/resources/static/**/*.css',
            'java/web/src/main/resources/templates/**/*.html',
            'scripts/quality/check_code_comment_language.py',
            'config/technical-terms.json',
        ],
        'pythonCompile': [
            'scripts/quality/check_session_detail_*.py',
            'scripts/quality/run_session_detail_*.py',
        ],
        'noTestSkips': [
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'playwright.config.js',
            'scripts/quality/check_no_test_skips.py',
        ],
        'templateContract': [
            'java/web/src/main/resources/templates/**',
            'tests/ui/test_web_template_contract.py',
            'scripts/quality/template_contract_check.py',
        ],
        'staticCssContract': [
            'java/web/src/main/resources/static/css/**/*.css',
            'tests/ui/test_web_static_contract.py',
            'scripts/quality/static_contract_check.py',
        ],
        'cssOwnership': [
            'java/web/src/main/resources/static/css/**/*.css',
            'scripts/quality/check_css_ownership.py',
        ],
        'rawInnerhtml': [
            'java/web/src/main/resources/static/**/*.js',
            'scripts/quality/check_raw_innerhtml.py',
        ],
        'layoutInlineStyle': [
            'java/web/src/main/resources/static/**/*.js',
            'scripts/quality/check_layout_inline_style.py',
        ],
        'pytest': [
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'tests/ui/**/*.py',
        ],
        'browserLayout': [
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'tests/playwright/**/*.js',
            'playwright.config.js',
        ],
        'browserInteraction': [
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'tests/playwright/**/*.js',
            'playwright.config.js',
        ],
    },
    'java-src': {
        'javaCheck': [
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
            '**/*.java',
        ],
        'javaModuleBoundaries': [
            'config/architecture/java-modules.yaml',
            'settings.gradle.kts',
            'java/**/build.gradle.kts',
            'java/**/src/main/java/**/*.java',
            '**/*.java',
        ],
        'javaChineseComments': [
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
            '**/*.java',
        ],
        'javaRecordComponentJavadocs': [
            'java/**/src/main/java/**/*.java',
            '**/*.java',
        ],
        'noJavaTestSkips': [
            'java/**/src/test/java/**/*.java',
        ],
        'noJavaSuppressWarnings': [
            'java/**/src/main/java/**/*.java',
        ],
        'reuseAnalyzeIncremental': [
            'java/**/src/main/java/**/*.java',
        ],
        'reuseStandardCpd': [
            'java/**/src/main/java/**/*.java',
            'config/reuse-policy/**',
        ],
    },
    'java-build': {
        'javaCheck': [
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
        ],
        'javaModuleBoundaries': [
            'config/architecture/java-modules.yaml',
            'settings.gradle.kts',
            'java/**/build.gradle.kts',
        ],
        'reuseAnalyzeIncremental': [
            'config/reuse-policy/**',
            'java/**/build.gradle.kts',
            'settings.gradle.kts',
            'build.gradle.kts',
        ],
        'reuseStandardCpd': [
            'config/reuse-policy/**',
            'java/**/build.gradle.kts',
            'settings.gradle.kts',
            'build.gradle.kts',
        ],
    },
    'scan-script-smoke': {
        'scanScriptSmoke': [
            'scripts/session-browser.sh',
            'java/app-cli/**',
            'java/scan-engine/**',
            'java/sources/**',
            'java/index-sqlite/**',
            'scripts/quality/**',
            'tests/script_commands/**',
        ],
        'sessionSamples': [
            'docs/session-samples/**',
            'java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**',
            'java/sources/**',
            'java/normalization-engine/**',
            'java/artifact-normalized/**',
            'java/tests/contracts/src/test/java/com/feipi/session/browser/contracttest/sample/**',
        ],
    },
}


# 规范化注释文本。
def _normalize(path: str) -> str:
    """参数：
        path: 待检查的路径。

    返回：
        Computed 结果。
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 维护glob 匹配。
def _glob_match(path: str, pattern: str) -> bool:
    """参数：
        path: 待检查的路径。
        pattern: 匹配用的 glob pattern。

    返回：
        Computed 结果。
    """
    p = _normalize(path)
    pat = _normalize(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', p))


# 维护pattern 匹配。
def _pattern_matches(path: str, pattern: str) -> bool:
    """参数：
        path: 待检查的路径。
        pattern: 匹配用的 glob pattern。

    返回：
        Computed 结果。
    """
    return _glob_match(path, pattern)


# 维护必需 gates target。
def required_gates_for_target(target: str) -> list[str]:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。

    返回：
        Computed 结果。
    """
    return list(QUALITY_TARGETS.get(target, []))


# 维护applicable gates target。
def applicable_gates_for_target(target: str, changed_files: list[str] | None = None) -> list[str]:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
        changed_files: 待检查的文件列表。

    返回：
        Computed 结果。
    """
    if changed_files is None:
        return required_gates_for_target(target)

    gate_patterns = GATE_PATTERNS.get(target, {})
    # 没有 trigger rule 的 baseline gate 仍运行，作为增量安全兜底。
    all_gates = set(required_gates_for_target(target))
    applicable: set[str] = set()

    for gate, patterns in gate_patterns.items():
        for f in changed_files:
            if any(_pattern_matches(f, pattern) for pattern in patterns):
                applicable.add(gate)
                break

    # 保持未定义 trigger 的 baseline gate 活跃，避免新 gate 被意外抑制。
    defined_gates = set(gate_patterns.keys())
    for gate in all_gates - defined_gates:
        applicable.add(gate)

    return [g for g in required_gates_for_target(target) if g in applicable]


# 验证target。
def validate_target(target: str) -> None:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。
    """
    if target not in QUALITY_TARGETS:
        raise ValueError(f'Unknown quality target: {target}')


# 维护有效 targets。
def effective_targets(targets: list[str]) -> list[str]:
    """参数：
        targets: 初始质量目标列表。

    返回：
        去重后的目标列表，保留原始顺序。

    说明：
        当 java-src 在列表中时，java-构建 会被移除，因为 java-src 的 Gradle。
        检查已经覆盖了 java-构建 需要的全部检查。
    """
    result: list[str] = list(targets)
    for t in targets:
        if t in TARGET_DOMINANCE:
            for included in TARGET_DOMINANCE[t]['includes']:
                if included in result:
                    result.remove(included)
    return result


# 维护target 并行 metadata。
def target_parallel_meta(target: str) -> dict[str, object]:
    """参数：
        target: 当前要运行或解析的 quality gate target 名称。

    返回：
        结果映射。
    """
    return dict(
        TARGET_META.get(target, {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300})
    )
