"""Classify changed repository files for Claude hook quality gates.

Post-write hooks call this module for each modified path. The output records category,
risk level, default allow status, and required quality target so stop hooks can decide
which local quality gate evidence is required before a session finishes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 01. 分类结果模型
@dataclass(frozen=True)
class FileClassification:
    """Describe hook policy and quality-gate metadata for one repository path.

    Attributes:
        file: Normalized repository-relative path.
        category: Classification category matched from ``RULES``.
        requires_quality_gate: Whether the path should trigger gate evidence.
        quality_target: Quality target name required by the path, when any.
        risk_level: User-facing risk level for hook summaries.
        allowed_by_default: Whether pre-write policy allows the path by default.
    """

    file: str
    category: str
    requires_quality_gate: bool
    quality_target: str | None
    risk_level: str
    allowed_by_default: bool


# 02. 分类规则
RULES: list[tuple[str, list[str], bool, str | None, str, bool]] = [
    (
        'acceptance-contract',
        ['docs/acceptance-contracts/**'],
        True,
        'acceptance-contracts',
        'medium',
        True,
    ),
    (
        'ui-template',
        ['src/session_browser/web/templates/**/*.html', 'src/session_browser/web/templates/*.html'],
        True,
        'session-detail',
        'medium',
        True,
    ),
    (
        'ui-css',
        ['src/session_browser/web/static/**/*.css', 'src/session_browser/web/static/*.css'],
        True,
        'session-detail',
        'medium',
        True,
    ),
    (
        'ui-js',
        ['src/session_browser/web/static/**/*.js', 'src/session_browser/web/static/*.js'],
        True,
        'session-detail',
        'medium',
        True,
    ),
    (
        'python-src',
        ['src/session_browser/**/*.py', 'src/session_browser/*.py'],
        True,
        'python-src',
        'medium',
        True,
    ),
    (
        'test',
        [
            'tests/**/*.py',
            'tests/*.py',
            'tests/**/*.js',
            'tests/*.js',
            'tests/**/*.ts',
            'tests/*.ts',
        ],
        True,
        'acceptance-contracts',
        'medium',
        True,
    ),
    (
        'hook',
        [
            '.claude/hooks/**',
            '.codex/hooks/**',
            '.qoder/hooks/**',
            'scripts/claude_hooks/**',
            'scripts/hooks/**',
            'scripts/agent_hooks/**',
        ],
        True,
        'hook-runtime',
        'high',
        True,
    ),
    ('quality-gate', ['scripts/quality/**'], True, 'hook-runtime', 'high', True),
    ('harness', ['harness/**', 'scripts/harness/**'], True, 'harness', 'high', True),
    ('openspec', ['openspec/**'], True, 'harness', 'medium', True),
    ('repo-script', ['scripts/*.sh', 'scripts/**/*.sh'], True, 'hook-runtime', 'high', True),
    (
        'python-tooling-config',
        [
            'pyproject.toml',
            'requirements*.txt',
            'requirements*.lock',
            'uv.lock',
            '.pre-commit-config.yaml',
            '.github/workflows/**',
        ],
        True,
        'hook-runtime',
        'high',
        True,
    ),
    (
        'agent-config',
        [
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
        ],
        True,
        'hook-runtime',
        'high',
        True,
    ),
    ('docs', ['README.md', 'docs/**'], False, None, 'low', True),
    (
        'local-or-generated',
        [
            'tmp/**',
            'data/**',
            'output/**',
            '.venv/**',
            '.pytest_cache/**',
            '**/*.sqlite',
            '**/*.sqlite3',
            '**/*.db',
        ],
        False,
        None,
        'local',
        True,
    ),
]


# 03. 路径规范化
def normalize_repo_path(path: str) -> str:
    """Normalize hook input paths before matching classification rules.

    Args:
        path: Repository or tool-provided path.

    Returns:
        Slash-separated repository-relative path without leading ``./`` or slashes.
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 04. glob 匹配: 使用正则支持 ** 语义。
def _glob_match(path: str, pattern: str) -> bool:
    """Match a path against a hook rule glob with ``**`` directory semantics.

    Args:
        path: Normalized repository path to test.
        pattern: Glob pattern from ``RULES``.

    Returns:
        ``True`` when the path matches the pattern; otherwise ``False``.
    """
    p = normalize_repo_path(path)
    pat = normalize_repo_path(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', p))


def _match(path: str, pattern: str) -> bool:
    """Return whether a file path matches a quality-gate rule pattern.

    Args:
        path: Normalized repository path to test.
        pattern: Glob pattern from ``RULES``.

    Returns:
        ``True`` when the path matches the pattern; otherwise ``False``.
    """
    return _glob_match(path, pattern)


# 05. 单文件分类
def classify_file(path: str) -> FileClassification:
    """Classify one changed file for hook enforcement.

    Args:
        path: File path reported by a write hook or quality check.

    Returns:
        Classification record with category, risk level, allow status, and required
        quality target. Unknown paths are allowed by default and do not trigger gates.
    """
    p = normalize_repo_path(path)
    for category, patterns, req, target, risk, allow in RULES:
        if any(_match(p, pattern) for pattern in patterns):
            return FileClassification(
                file=p,
                category=category,
                requires_quality_gate=req,
                quality_target=target,
                risk_level=risk,
                allowed_by_default=allow,
            )
    return FileClassification(
        file=p,
        category='unknown',
        requires_quality_gate=False,
        quality_target=None,
        risk_level='low',
        allowed_by_default=True,
    )


# 06. 多文件目标汇总
def required_quality_targets(files: list[str]) -> list[str]:
    """Collect quality targets required by a batch of changed files.

    Args:
        files: Changed file paths from hook evidence.

    Returns:
        Ordered, de-duplicated quality targets. The order follows first occurrence in
        hook evidence so user-facing remediation commands stay deterministic.
    """
    targets: list[str] = []
    for f in files:
        c = classify_file(f)
        if c.requires_quality_gate and c.quality_target and c.quality_target not in targets:
            targets.append(c.quality_target)
    return targets


# 07. 自测试
def _self_test() -> None:
    """Run local assertions for path classification edge cases."""
    assert (
        classify_file('src/session_browser/web/templates/session_detail.html').category
        == 'ui-template'
    )
    assert classify_file('src/session_browser/web/static/app.css').category == 'ui-css'
    assert classify_file('src/session_browser/foo.py').quality_target == 'python-src'
    assert (
        classify_file('docs/acceptance-contracts/features/DATA_PRESENTERS.md').quality_target
        == 'acceptance-contracts'
    )
    assert (
        classify_file('tests/backend/test_round_signals.py').quality_target
        == 'acceptance-contracts'
    )
    assert classify_file('.claude/settings.json').quality_target == 'hook-runtime'
    assert classify_file('.codex/hooks/stop_check.sh').quality_target == 'hook-runtime'
    assert classify_file('.qoder/hooks/stop_check.sh').quality_target == 'hook-runtime'
    assert classify_file('scripts/session-browser.sh').quality_target == 'hook-runtime'
    assert classify_file('.codex/config.toml').quality_target == 'hook-runtime'
    assert classify_file('pyproject.toml').quality_target == 'hook-runtime'
    assert classify_file('requirements-dev.lock').quality_target == 'hook-runtime'
    assert classify_file('uv.lock').quality_target == 'hook-runtime'
    assert classify_file('.pre-commit-config.yaml').quality_target == 'hook-runtime'
    assert classify_file('.github/workflows/quality.yml').quality_target == 'hook-runtime'
    assert (
        classify_file('skills/authoring/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert (
        classify_file('.agents/skills/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert (
        classify_file('.codex/skills/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert (
        classify_file('.claude/skills/feipi-openspec-orchestrate-change/SKILL.md').quality_target
        == 'hook-runtime'
    )
    assert classify_file('AGENTS.md').quality_target == 'hook-runtime'
    assert classify_file('CLAUDE.md').quality_target == 'hook-runtime'
    assert classify_file('tmp/agent_logs/session1/x.jsonl').category == 'local-or-generated'
