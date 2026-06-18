from __future__ import annotations


# 01. target -> required gate 矩阵（全量 baseline）
QUALITY_TARGETS: dict[str, list[str]] = {
    "session-detail": [
        "pythonCompile",
        "noTestSkips",
        "templateContract",
        "staticCssContract",
        "cssOwnership",
        "browserLayout",
        "browserInteraction",
        "rawInnerhtml",
        "layoutInlineStyle",
        "pytest",
    ],
    "python-src": [
        "pythonCompile",
        "pytest",
    ],
    "hook-runtime": [
        "settingsJson",
        "bashSyntax",
        "pythonCompile",
        "noTestSkips",
        "languagePolicy",
        "codexAgentPolicy",
        "hookSelfTest",
        "pytest",
        "doctor",
        "repoStructure",
        "repoSlimming",
        "rawInnerhtml",
        "layoutInlineStyle",
        "acceptanceContracts",
    ],
    "harness": [
        "bashSyntax",
        "pythonCompile",
        "noTestSkips",
        "languagePolicy",
        "codexAgentPolicy",
        "doctor",
        "repoStructure",
        "harnessStructure",
        "openspecLayout",
    ],
    "acceptance-contracts": [
        "noTestSkips",
        "acceptanceContracts",
        "pytest",
    ],
    "index": [
        "indexIntegrity",
    ],
}


# 02. gate -> 文件模式映射（增量触发）
# 只有当 changed-files 中至少一个文件匹配 gate 的模式时，才运行该 gate。
# 如果没有提供 changed-files 列表（如手动运行 --target），则回退到全量 baseline。
GATE_PATTERNS: dict[str, dict[str, list[str]]] = {
    "session-detail": {
        "templateContract": [
            "src/session_browser/web/templates/**/*.html",
        ],
        "staticCssContract": [
            "src/session_browser/web/static/**/*.css",
        ],
        "cssOwnership": [
            "src/session_browser/web/static/**/*.css",
        ],
        "browserLayout": [
            "src/session_browser/web/templates/**/*.html",
            "src/session_browser/web/static/**/*.css",
        ],
        "browserInteraction": [
            "src/session_browser/web/static/**/*.js",
        ],
        "rawInnerhtml": [
            "src/session_browser/web/static/**/*.js",
        ],
        "layoutInlineStyle": [
            "src/session_browser/web/templates/**/*.html",
            "src/session_browser/web/static/**/*.js",
        ],
        "pythonCompile": [
            "src/session_browser/**/*.py",
        ],
        "noTestSkips": [
            "tests/**/*.py",
            "tests/**/*.js",
            "tests/**/*.ts",
            "playwright.config.js",
            "scripts/quality/check_no_test_skips.py",
        ],
    },
    "python-src": {
        "pythonCompile": [
            "src/session_browser/**/*.py",
        ],
    },
    "hook-runtime": {
        "settingsJson": [
            ".claude/settings.json",
            ".claude/settings.local.json",
            ".codex/hooks.json",
        ],
        "bashSyntax": [
            ".claude/hooks/**/*.sh",
            ".codex/hooks/**/*.sh",
            ".qoder/hooks/**/*.sh",
            "scripts/hooks/**/*.sh",
            "scripts/agent_hooks/**/*.sh",
        ],
        "pythonCompile": [
            "scripts/claude_hooks/**/*.py",
            "scripts/hooks/**/*.py",
            "scripts/agent_hooks/**/*.py",
            "scripts/quality/**/*.py",
        ],
        "noTestSkips": [
            "tests/**/*.py",
            "tests/**/*.js",
            "tests/**/*.ts",
            "playwright.config.js",
            "scripts/quality/check_no_test_skips.py",
        ],
        "hookSelfTest": [
            "scripts/claude_hooks/**/*.py",
        ],
        "pytest": [
            "scripts/claude_hooks/**/*.py",
            "scripts/hooks/**/*.py",
            "scripts/agent_hooks/**/*.py",
            "scripts/quality/**/*.py",
        ],
        "doctor": [
            ".claude/hooks/**/*.sh",
            ".codex/hooks/**/*.sh",
            ".qoder/hooks/**/*.sh",
            ".claude/settings.json",
            "scripts/**/*.sh",
        ],
        "repoStructure": [
            ".claude/**",
            ".codex/**",
            "skills/**",
            ".agents/skills/**",
            ".qoder/**",
            "scripts/**/*.py",
            "scripts/**/*.sh",
            "AGENTS.md",
            "CLAUDE.md",
            "README.md",
            "docs/**",
        ],
        "repoSlimming": [
            "src/session_browser/web/static/**/*.css",
            "src/session_browser/web/static/**/*.js",
            "src/session_browser/web/static/css/**/*.css",
            "harness/**",
            "openspec/**",
            "tests/**/*.py",
            "src/session_browser/web/templates/**/*.html",
            "scripts/quality/repo_slimming_contract_check.py",
            "tests/quality/test_repo_slimming_contract.py",
        ],
        "rawInnerhtml": [
            "src/session_browser/web/static/**/*.js",
            "scripts/quality/check_raw_innerhtml.py",
        ],
        "layoutInlineStyle": [
            "src/session_browser/web/templates/**/*.html",
            "src/session_browser/web/static/**/*.js",
            "scripts/quality/check_layout_inline_style.py",
        ],
        "acceptanceContracts": [
            "scripts/quality/validate_acceptance_contracts.py",
            "tests/quality/test_contract_case_specs.py",
        ],
        "languagePolicy": [
            "AGENTS.md",
            "CLAUDE.md",
            "skills/**",
            ".agents/skills/**",
            ".codex/**",
            ".claude/agents/**",
            ".claude/skills/**",
            ".qoder/**",
            "harness/**",
            "openspec/changes/**",
            "scripts/quality/check_language_policy.py",
        ],
        "codexAgentPolicy": [
            ".codex/agents/**",
            "scripts/quality/check_codex_agent_policy.py",
        ],
    },
    "harness": {
        "bashSyntax": [
            "scripts/harness/**/*.sh",
        ],
        "pythonCompile": [
            "scripts/harness/**/*.py",
            "scripts/quality/**/*.py",
        ],
        "noTestSkips": [
            "tests/**/*.py",
            "tests/**/*.js",
            "tests/**/*.ts",
            "playwright.config.js",
            "scripts/quality/check_no_test_skips.py",
        ],
        "doctor": [
            "scripts/harness/**/*.sh",
        ],
        "repoStructure": [
            "scripts/harness/**",
        ],
        "harnessStructure": [
            "harness/**",
            "scripts/harness/**/*.py",
        ],
        "openspecLayout": [
            "openspec/**",
        ],
        "languagePolicy": [
            "AGENTS.md",
            "CLAUDE.md",
            "skills/**",
            ".agents/skills/**",
            ".codex/**",
            ".claude/agents/**",
            ".claude/skills/**",
            ".qoder/**",
            "harness/**",
            "openspec/changes/**",
            "scripts/quality/check_language_policy.py",
        ],
        "codexAgentPolicy": [
            ".codex/agents/**",
            "scripts/quality/check_codex_agent_policy.py",
        ],
    },
    "index": {
        "indexIntegrity": [
            "src/session_browser/index/**/*.py",
            "src/session_browser/config.py",
            "scripts/quality/check_index_integrity.py",
        ],
    },
    "acceptance-contracts": {
        "noTestSkips": [
            "tests/**/*.py",
            "tests/**/*.js",
            "tests/**/*.ts",
            "playwright.config.js",
            "scripts/quality/check_no_test_skips.py",
        ],
        "acceptanceContracts": [
            "docs/acceptance-contracts/**/*.md",
            "tests/**/*.py",
            "tests/**/*.js",
            "tests/**/*.ts",
            "scripts/quality/validate_acceptance_contracts.py",
            "tests/quality/test_contract_case_specs.py",
            "pyproject.toml",
        ],
        "pytest": [
            "docs/acceptance-contracts/**/*.md",
            "tests/**/*.py",
            "tests/**/*.js",
            "tests/**/*.ts",
            "scripts/quality/validate_acceptance_contracts.py",
            "tests/quality/test_contract_case_specs.py",
            "pyproject.toml",
        ],
    },
}


# 03. 路径规范化与 glob 匹配
def _normalize(path: str) -> str:
    value = path.replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.strip("/")


def _glob_match(path: str, pattern: str) -> bool:
    """支持 ** 语义的 glob 匹配。** 匹配零或多个目录段。"""
    import re
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
    """Return whether a normalized path matches a quality gate pattern."""
    return _glob_match(path, pattern)


# 04. 查询函数
def required_gates_for_target(target: str) -> list[str]:
    return list(QUALITY_TARGETS.get(target, []))


def applicable_gates_for_target(target: str, changed_files: list[str] | None = None) -> list[str]:
    """根据实际修改的文件，返回该 target 下应该运行的 gates。

    如果没有提供 changed_files（None），回退到全量 baseline。
    如果提供了 changed_files，只返回至少有一个文件匹配该 gate 模式的 gates。
    """
    if changed_files is None:
        return required_gates_for_target(target)

    gate_patterns = GATE_PATTERNS.get(target, {})
    # 全量 baseline 中的 gate，如果没有在 GATE_PATTERNS 中定义，也默认运行（安全兜底）
    all_gates = set(required_gates_for_target(target))
    applicable: set[str] = set()

    for gate, patterns in gate_patterns.items():
        for f in changed_files:
            if any(_pattern_matches(f, pattern) for pattern in patterns):
                applicable.add(gate)
                break

    # 安全兜底：GATE_PATTERNS 中未定义的 gate，如果在全量 baseline 中存在，默认运行
    defined_gates = set(gate_patterns.keys())
    for gate in all_gates - defined_gates:
        applicable.add(gate)

    return [g for g in required_gates_for_target(target) if g in applicable]


# 05. target 校验
def validate_target(target: str) -> None:
    if target not in QUALITY_TARGETS:
        raise ValueError(f"未知 quality target：{target}")
