"""Map quality targets to required gates and changed-file trigger patterns.

Targets are named validation surfaces such as `python-standard` or `harness`.
Each target owns an ordered baseline gate list, while trigger patterns narrow
which gates run when callers provide changed files. Gates missing trigger
patterns keep running as a safe default so incremental checks do not silently
drop required coverage.
"""

from __future__ import annotations

import re

# 01. target -> required gate matrix (full baseline)
QUALITY_TARGETS: dict[str, list[str]] = {
    'session-detail': [
        'pythonCompile',
        'noTestSkips',
        'templateContract',
        'staticCssContract',
        'cssOwnership',
        'browserLayout',
        'browserInteraction',
        'rawInnerhtml',
        'layoutInlineStyle',
        'pytest',
    ],
    'python-src': [
        'pythonCompile',
        'pytest',
    ],
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
        'settingsJson',
        'bashSyntax',
        'pythonCompile',
        'noTestSkips',
        'languagePolicy',
        'codexAgentPolicy',
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
        'pythonCompile',
        'noTestSkips',
        'languagePolicy',
        'codexAgentPolicy',
        'doctor',
        'repoStructure',
        'harnessStructure',
        'openspecLayout',
    ],
    'acceptance-contracts': [
        'noTestSkips',
        'acceptanceContracts',
        'pytest',
    ],
    'index': [
        'indexIntegrity',
    ],
    'java-src': [
        'javaCheck',
        'javaChineseComments',
        'noJavaTestSkips',
        'reuseIncremental',
        'reuseBaselineVerify',
    ],
    'java-build': [
        'javaCheck',
    ],
}

# 01b. target 并行执行元数据
# parallel_safe: 是否可与其他无冲突 target 并行执行
# exclusive_resources: 互斥资源列表（如 gradle-daemon），同一资源同时只允许一个 target 使用
# timeout: 单 target 最大执行时间（秒）
TARGET_META: dict[str, dict[str, object]] = {
    'session-detail': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300},
    'python-src': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'python-standard': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300},
    'hook-runtime': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300},
    'harness': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'acceptance-contracts': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'index': {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 120},
    'java-src': {'parallel_safe': True, 'exclusive_resources': ['gradle-daemon'], 'timeout': 600},
    'java-build': {'parallel_safe': True, 'exclusive_resources': ['gradle-daemon'], 'timeout': 300},
}

# 01c. target dominance 声明: 当 dominant target 触发时自动包含 dominated target
# java-src 包含 java-build，避免两个 target 各自运行一次 Gradle baseline
TARGET_DOMINANCE: dict[str, dict[str, list[str]]] = {
    'java-src': {'includes': ['java-build']},
}


# 02. gate -> file pattern map (incremental trigger)
# A gate runs only when at least one changed file matches one of its patterns.
# If callers omit changed files, such as manual --target runs, use the full baseline.
GATE_PATTERNS: dict[str, dict[str, list[str]]] = {
    'session-detail': {
        'templateContract': [
            'src/session_browser/web/templates/**/*.html',
        ],
        'staticCssContract': [
            'src/session_browser/web/static/**/*.css',
        ],
        'cssOwnership': [
            'src/session_browser/web/static/**/*.css',
        ],
        'browserLayout': [
            'src/session_browser/web/templates/**/*.html',
            'src/session_browser/web/static/**/*.css',
        ],
        'browserInteraction': [
            'src/session_browser/web/static/**/*.js',
        ],
        'rawInnerhtml': [
            'src/session_browser/web/static/**/*.js',
        ],
        'layoutInlineStyle': [
            'src/session_browser/web/templates/**/*.html',
            'src/session_browser/web/static/**/*.js',
        ],
        'pythonCompile': [
            'src/session_browser/**/*.py',
        ],
        'noTestSkips': [
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'playwright.config.js',
            'scripts/quality/check_no_test_skips.py',
        ],
    },
    'python-src': {
        'pythonCompile': [
            'src/session_browser/**/*.py',
        ],
    },
    'python-standard': {
        'pythonFormat': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonLint': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonType': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
            'scripts/**/*.py',
            'tests/**/*.py',
        ],
        'pythonDocstring': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
            'scripts/**/*.py',
        ],
        'pythonCoverage': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
            'tests/**/*.py',
        ],
        'pythonAudit': [
            'pyproject.toml',
            'requirements*.txt',
            'requirements*.lock',
            'uv.lock',
            'src/session_browser/**/*.py',
            'scripts/**/*.py',
        ],
        'pythonComplexity': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
            'scripts/**/*.py',
        ],
        'pythonDeadCode': [
            'pyproject.toml',
            'src/session_browser/**/*.py',
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
        'settingsJson': [
            '.claude/settings.json',
            '.claude/settings.local.json',
            '.codex/hooks.json',
        ],
        'bashSyntax': [
            '.claude/hooks/**/*.sh',
            '.codex/hooks/**/*.sh',
            '.qoder/hooks/**/*.sh',
            'scripts/hooks/**/*.sh',
            'scripts/agent_hooks/**/*.sh',
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
            'src/session_browser/web/static/**/*.css',
            'src/session_browser/web/static/**/*.js',
            'src/session_browser/web/static/css/**/*.css',
            'harness/**',
            'openspec/**',
            'tests/**/*.py',
            'src/session_browser/web/templates/**/*.html',
            'scripts/quality/repo_slimming_contract_check.py',
            'tests/quality/test_repo_slimming_contract.py',
        ],
        'rawInnerhtml': [
            'src/session_browser/web/static/**/*.js',
            'scripts/quality/check_raw_innerhtml.py',
        ],
        'layoutInlineStyle': [
            'src/session_browser/web/templates/**/*.html',
            'src/session_browser/web/static/**/*.js',
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
    },
    'harness': {
        'bashSyntax': [
            'scripts/harness/**/*.sh',
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
    },
    'index': {
        'indexIntegrity': [
            'src/session_browser/index/**/*.py',
            'src/session_browser/config.py',
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
    'java-src': {
        'javaCheck': [
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
            '**/*.java',
        ],
        'javaChineseComments': [
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
            '**/*.java',
        ],
        'noJavaTestSkips': [
            'java/**/src/test/java/**/*.java',
        ],
        'reuseIncremental': [
            'java/**/src/main/java/**/*.java',
        ],
        'reuseBaselineVerify': [
            'java/**/src/main/java/**/*.java',
        ],
    },
    'java-build': {
        'javaCheck': [
            'build-logic/**',
            'gradle/**',
            'build.gradle.kts',
            'settings.gradle.kts',
            'gradle.properties',
            'gradlew',
            'gradlew.bat',
            '*.lockfile',
        ],
    },
}


# 03. path normalization and glob matching
def _normalize(path: str) -> str:
    """Normalize a repository path before comparing it with trigger patterns.

    Args:
        path: Input value for path.

    Returns:
        Computed result.
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def _glob_match(path: str, pattern: str) -> bool:
    """Return whether a path matches the gate glob, including `**` directory spans.

    Args:
        path: Input value for path.
        pattern: Input value for pattern.

    Returns:
        Computed result.
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


def _pattern_matches(path: str, pattern: str) -> bool:
    """Return whether a normalized path matches a quality gate pattern.

    Args:
        path: Input value for path.
        pattern: Input value for pattern.

    Returns:
        Computed result.
    """
    return _glob_match(path, pattern)


# 04. query functions
def required_gates_for_target(target: str) -> list[str]:
    """Return the ordered baseline gates required for a quality target.

    Args:
        target: Input value for target.

    Returns:
        Computed result.
    """
    return list(QUALITY_TARGETS.get(target, []))


def applicable_gates_for_target(target: str, changed_files: list[str] | None = None) -> list[str]:
    """Return gates to run for a target after applying changed-file triggers.

    Args:
        target: Input value for target.
        changed_files: Input value for changed_files.

    Returns:
        Computed result.
    """
    if changed_files is None:
        return required_gates_for_target(target)

    gate_patterns = GATE_PATTERNS.get(target, {})
    # Baseline gates without trigger rules still run as an incremental safety fallback.
    all_gates = set(required_gates_for_target(target))
    applicable: set[str] = set()

    for gate, patterns in gate_patterns.items():
        for f in changed_files:
            if any(_pattern_matches(f, pattern) for pattern in patterns):
                applicable.add(gate)
                break

    # Keep undefined baseline gates active so new gates are not accidentally suppressed.
    defined_gates = set(gate_patterns.keys())
    for gate in all_gates - defined_gates:
        applicable.add(gate)

    return [g for g in required_gates_for_target(target) if g in applicable]


# 05. target validation
def validate_target(target: str) -> None:
    """Raise when a caller requests an unknown quality target.

    Args:
        target: Input value for target.

    Raises:
        ValueError: Raised when validation fails.
    """
    if target not in QUALITY_TARGETS:
        raise ValueError(f'Unknown quality target: {target}')


# 06. dominance 去重
def effective_targets(targets: list[str]) -> list[str]:
    """Apply dominance rules to remove redundant quality targets.

    当 java-src 在列表中时，java-build 会被移除，因为 java-src 的 Gradle
    检查已经覆盖了 java-build 需要的全部检查。

    Args:
        targets: 初始质量目标列表。

    Returns:
        去重后的目标列表，保留原始顺序。
    """
    result: list[str] = list(targets)
    for t in targets:
        if t in TARGET_DOMINANCE:
            for included in TARGET_DOMINANCE[t]['includes']:
                if included in result:
                    result.remove(included)
    return result


# 07. 并行元数据查询
def target_parallel_meta(target: str) -> dict[str, object]:
    """Return parallel execution metadata for a quality target.

    Args:
        target: Quality target name.

    Returns:
        Metadata dict with parallel_safe, exclusive_resources, and timeout.
    """
    return dict(TARGET_META.get(target, {'parallel_safe': True, 'exclusive_resources': [], 'timeout': 300}))
