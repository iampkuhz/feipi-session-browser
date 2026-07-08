"""提供 classify 脚本能力。"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 01. 分类结果模型
@dataclass(frozen=True)
class FileClassification:
    """表示 FileClassification。

    属性：
        file: 待检查的文件。
        category: 文件分类。
        requires_quality_gate: 该路径是否触发 quality gate evidence。
        quality_target: 需要运行的 quality target。
        risk_level: 面向用户展示的风险等级。
        allowed_by_default: 默认策略是否允许该路径。
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
        'java-src',
        [
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
        ],
        True,
        'java-src',
        'medium',
        True,
    ),
    (
        'java-build',
        [
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
        ],
        True,
        'java-build',
        'medium',
        True,
    ),
    (
        'java-root-dsl',
        [
            'build.gradle.kts',
            'gradle.properties',
        ],
        True,
        'java-build',
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
        'session-detail-ui',
        [
            'java/web/src/main/resources/static/**',
            'java/web/src/main/resources/templates/**',
            'src/session_browser/web/**',
            'scripts/quality/check_session_detail_*.py',
            'scripts/quality/run_session_detail_*.py',
        ],
        True,
        'session-detail',
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
    # 未知 Java/Gradle 路径 fail closed：不在已知模式内的 Java 文件仍需质量门控
    (
        'java-src-unknown',
        ['**/*.java'],
        True,
        'java-src',
        'high',
        False,
    ),
    (
        'java-build-unknown',
        ['**/*.gradle', '**/*.gradle.kts'],
        True,
        'java-build',
        'high',
        False,
    ),
]


# 规范化repo 路径。
def normalize_repo_path(path: str) -> str:
    """参数：
        path: 待检查的路径。

    返回：
        normalize repo 路径 字符串。
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 维护glob 匹配。
def _glob_match(path: str, pattern: str) -> bool:
    """参数：
        path: 规范化 repository 路径到test。
        pattern: 匹配用的 glob pattern。

    返回：
        满足条件时返回 true，否则返回 false。
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


# 维护匹配。
def _match(path: str, pattern: str) -> bool:
    """参数：
        path: 规范化 repository 路径到test。
        pattern: 匹配用的 glob pattern。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    return _glob_match(path, pattern)


# 分类文件。
def classify_file(path: str) -> FileClassification:
    """参数：
        path: 文件路径 reported by 写入 hook 或 quality 检查。

    返回：
        Classification record带category, risk level, allow 状态, 和 必需。 quality target. Unknown 路径 are allowed by 默认 和 do 不 trigger gate。
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


# 维护必需 quality targets。
def required_quality_targets(files: list[str]) -> list[str]:
    """参数：
        files: Changed 文件路径s从hook evidence。

    返回：
        结果列表。
    """
    targets: list[str] = []
    for f in files:
        c = classify_file(f)
        if c.requires_quality_gate and c.quality_target and c.quality_target not in targets:
            targets.append(c.quality_target)
    # 当 scan-related 文件 change, 不带 replacing 现有 mappings。
    for f in files:
        for pattern in SCAN_SCRIPT_SMOKE_PATTERNS:
            if _match(f, pattern):
                if 'scan-script-smoke' not in targets:
                    targets.append('scan-script-smoke')
                break
    return targets


# in addition到whatever primary target the 文件 maps 到。
SCAN_SCRIPT_SMOKE_PATTERNS: list[str] = [
    'scripts/session-browser.sh',
    'java/app-cli/**',
    'java/scan-engine/**',
    'java/sources/**',
    'java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**',
    'java/normalization-engine/**',
    'java/artifact-normalized/**',
    'java/index-sqlite/**',
    'docs/session-samples/**',
    'scripts/quality/**',
]


# 07. target dominance 声明: 当 java-src 触发时自动包含 java-build，避免重复 Gradle 基线
DOMINANCE: dict[str, dict[str, list[str]]] = {
    'java-src': {'includes': ['java-build']},
}


# 维护有效 targets。
def effective_targets(targets: list[str]) -> list[str]:
    """参数：
        targets: 初始质量目标列表。

    返回：
        去重后的目标列表，保留原始顺序。

    说明：
        当一个 target 声明 includes 另一个 target 时，被包含的 target 不需要单独运行。
        重复的 Gradle 基线检查。
    """
    expanded: list[str] = list(targets)
    for t in targets:
        if t in DOMINANCE:
            for included in DOMINANCE[t]['includes']:
                if included in expanded:
                    expanded.remove(included)
    return expanded


# 运行脚本自测试场景。
def _self_test() -> None:
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
    assert (
        classify_file('java/web/src/main/resources/static/css/session-detail.css').quality_target
        == 'session-detail'
    )
    assert classify_file('tmp/agent_logs/session1/x.jsonl').category == 'local-or-generated'
    assert (
        classify_file('java/core-domain/src/main/java/com/feipi/Foo.java').quality_target
        == 'java-src'
    )
    assert (
        classify_file('java/tests/architecture/src/test/java/com/feipi/BarTest.java').quality_target
        == 'java-src'
    )
    assert (
        classify_file('build-logic/src/main/kotlin/feipi.java-base.gradle.kts').quality_target
        == 'java-build'
    )
    assert classify_file('gradle/libs.versions.toml').quality_target == 'java-build'
    assert classify_file('build.gradle.kts').quality_target == 'java-build'
    assert classify_file('gradle.properties').quality_target == 'java-build'
    assert classify_file('settings.gradle.kts').quality_target == 'java-build'
    assert classify_file('config/api-snapshots/java-public-api.txt').quality_target == 'java-build'
    # Windows 路径 normalization。
    assert (
        classify_file('java\\core-domain\\src\\main\\java\\com\\feipi\\Foo.java').quality_target
        == 'java-src'
    )
    assert classify_file('gradlew').quality_target == 'java-build'
    assert classify_file('gradlew').category == 'java-build'
    assert classify_file('gradlew.bat').quality_target == 'java-build'
    assert classify_file('settings-gradle.lockfile').quality_target == 'java-build'
    # Fail-closed用于unknown Java/Gradle 路径。
    c_unknown_java = classify_file('some/random/file.java')
    assert c_unknown_java.quality_target == 'java-src'
    assert c_unknown_java.requires_quality_gate is True
    assert c_unknown_java.allowed_by_default is False
    c_unknown_gradle = classify_file('random.gradle.kts')
    assert c_unknown_gradle.quality_target == 'java-build'
    assert c_unknown_gradle.requires_quality_gate is True
    assert c_unknown_gradle.allowed_by_default is False
    assert effective_targets(['java-src', 'java-build']) == ['java-src']
    assert effective_targets(['java-build']) == ['java-build']
    assert effective_targets(['java-src', 'hook-runtime']) == ['java-src', 'hook-runtime']
