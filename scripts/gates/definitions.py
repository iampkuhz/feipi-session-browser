"""负责集中声明当前 Gate、Target、Trigger 与执行 recipe。

维护 Gate 时只改本文件；本模块不负责选择 Gate、执行命令或解析外部配置，由 Catalog 校验并供
Planner、Executor 调用。声明使用不可变领域类型，避免 YAML 字段、分片索引和兼容 parser 增加维护跳转。
"""

from __future__ import annotations

from scripts.gates.model import (
    GateCatalog,
    GateSpec,
    GateTrigger,
    RunKind,
    RunSpec,
    RunStep,
    RunTargets,
    TargetSpec,
    TriggerMode,
)


def changed(*paths: str) -> GateTrigger:
    """声明只在 incremental 改动路径命中时自动选择的 Gate。"""
    return GateTrigger(TriggerMode.CHANGED, paths)


def run(incremental: int, full: int, *steps: RunStep) -> RunSpec:
    """绑定唯一 recipe 与两种扫描范围的非阻断时效目标。"""
    return RunSpec(RunTargets(incremental, full), steps)


def command(
    name: str,
    *argv: str,
    required_paths: tuple[str, ...] = (),
    append_globs: tuple[str, ...] = (),
) -> RunStep:
    """声明由外部标准工具执行的命令 leaf。"""
    return RunStep(
        name, RunKind.COMMAND, argv=argv, required_paths=required_paths, append_globs=append_globs
    )


def python_check(name: str, check_id: str, *args: str, runtime: str = 'system') -> RunStep:
    """声明由 Gate Python check registry 执行的领域 leaf。"""
    return RunStep(name, RunKind.PYTHON_CHECK, check_id=check_id, runtime=runtime, args=args)


def gradle_task(name: str, task: str, *args: str) -> RunStep:
    """声明只拥有一个 Gradle task 的 leaf。"""
    return RunStep(name, RunKind.GRADLE_TASK, tasks=(task,), args=args)


def java_rule(name: str, rule: str) -> RunStep:
    """声明只拥有一个 Java quality rule 的 leaf。"""
    return RunStep(name, RunKind.JAVA_RULE, rules=(rule,))


def playwright(name: str, tests: tuple[str, ...], *args: str) -> RunStep:
    """声明固定 Playwright suite 的 leaf。"""
    return RunStep(name, RunKind.PLAYWRIGHT, tests=tests, args=args)


def scan_smoke(
    name: str, tests: tuple[str, ...], prerequisite_tasks: tuple[str, ...], *args: str
) -> RunStep:
    """声明需要先准备 Java distribution 的扫描 smoke leaf。"""
    return RunStep(
        name,
        RunKind.SCAN_SMOKE,
        tests=tests,
        prerequisite_tasks=prerequisite_tasks,
        args=args,
    )


# Target 只供维护者人工选择一组 Gate，不参与 incremental 自动规划。
TARGETS = (
    TargetSpec('python-standard', '人工运行 Python 工具链与质量基础设施相关 Gate。'),
    TargetSpec('harness', '人工运行 Agent、Skill、Harness 与 OpenSpec 治理 Gate。'),
    TargetSpec('session-detail', '人工运行 Web 页面、静态资源与浏览器交互 Gate。'),
    TargetSpec('java-src', '人工运行 Java 源码与测试质量 Gate。'),
    TargetSpec('java-build', '人工运行 Gradle 构建与 Java 工程配置 Gate。'),
    TargetSpec('scan-script-smoke', '人工运行扫描命令、发行 CLI 与样本集成 Gate。'),
)


# Gate 按 README 展示和 full 执行顺序分组；每个 Gate 只有一个 recipe。
GATES = (
    GateSpec(
        name='scriptSourceStandard',
        description='统一检查 Python 格式、静态问题、依赖声明、安全与死代码，以及 Shell 语法。',
        trigger=changed(
            'pyproject.toml',
            'scripts/**/*.py',
            'tests/**/*.py',
            'scripts/**/*.sh',
        ),
        targets=('python-standard',),
        run=run(
            80,
            165,
            command(
                'pythonFormat',
                '{dev_python}',
                '-m',
                'ruff',
                'format',
                '--check',
                '.',
            ),
            command(
                'pythonLint',
                '{dev_python}',
                '-m',
                'ruff',
                'check',
                '.',
            ),
            command(
                'bashSyntax',
                'bash',
                '-n',
                append_globs=('scripts/**/*.sh',),
            ),
            command(
                'pythonDependencyDeclarations',
                '{dev_python}',
                '-m',
                'deptry',
                'scripts',
            ),
            command(
                'pythonSourceSecurity',
                '{dev_python}',
                '-m',
                'bandit',
                '-q',
                '-c',
                'pyproject.toml',
                '-r',
                'scripts',
                '--severity-level',
                'high',
            ),
            command(
                'pythonDeadCode',
                '{dev_python}',
                '-m',
                'vulture',
            ),
        ),
    ),
    GateSpec(
        name='pythonHarnessTests',
        description='运行 Harness、Gate 与质量契约的固定 Pytest 单测集合。',
        trigger=changed(
            'pyproject.toml',
            'scripts/gates/**/*.py',
            'scripts/gates/checks/**/*.py',
            'scripts/harness/**/*.py',
            'scripts/openspec/**/*.py',
            'tests/gates/**/*.py',
            'tests/checks/**/*.py',
            'tests/harness/**/*.py',
            'tests/misc/**/*.py',
            'tests/quality/**/*.py',
            'tests/*.py',
        ),
        targets=('python-standard',),
        run=run(
            60,
            180,
            command(
                'pythonHarnessTests',
                '{dev_python}',
                '-m',
                'pytest',
                '-W',
                'error',
                'tests/harness',
                'tests/gates',
                'tests/checks',
                'tests/quality',
                'tests/misc',
                required_paths=(
                    'tests/harness',
                    'tests/gates',
                    'tests/checks',
                    'tests/quality',
                    'tests/misc',
                ),
                append_globs=('tests/test_*.py',),
            ),
        ),
    ),
    GateSpec(
        name='pythonDependencyVulnerabilities',
        description='审计 Python 锁定依赖中的已知漏洞。',
        trigger=changed(
            'pyproject.toml',
            'uv.lock',
        ),
        targets=('python-standard',),
        run=run(
            60,
            120,
            python_check(
                'pythonDependencyVulnerabilities',
                'repository.python-dependency-vulnerabilities',
                '--root',
                '{repo_root}',
                runtime='dev',
            ),
        ),
    ),
    GateSpec(
        name='repositoryFilePolicy',
        description='统一检查仓库文件、退役路径、Git 追踪和公开脚本入口边界。',
        trigger=changed(
            '.gitignore',
            'AGENTS.md',
            'CLAUDE.md',
            '.github/**',
            '.agents/**',
            '.claude/**',
            '.codex/**',
            '.qoder/**',
            'docs/**',
            'harness/**',
            'skills/**',
            'src/session_browser/**',
            'scripts/README.md',
            'scripts/gates/**',
        ),
        targets=('python-standard',),
        run=run(
            15,
            30,
            python_check(
                'repositoryFilePolicy',
                'repository.repository-file-policy',
                '--root',
                '{repo_root}',
                '--all-tracked',
            ),
        ),
    ),
    GateSpec(
        name='noPythonPlaywrightSkips',
        description='阻止 Python 与 Playwright 测试使用会产生 skipped 结果的 API。',
        trigger=changed(
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'tests/playwright/playwright.config.js',
            'scripts/gates/checks/repository/check_no_python_playwright_skips.py',
        ),
        targets=('session-detail',),
        run=run(
            8,
            15,
            python_check(
                'noPythonPlaywrightSkips',
                'repository.no-python-playwright-skips',
            ),
        ),
    ),
    GateSpec(
        name='currentSourcePolicy',
        description='检查仓库只描述当前版本和当前 Harness 状态。',
        trigger=changed(
            'README.md',
            'docs/**',
            'harness/**',
            'java/**',
            'openspec/specs/**',
            'scripts/**',
            'tests/**/*.py',
            'scripts/gates/checks/repository/check_current_source_policy.py',
            'tests/quality/test_current_source_policy.py',
        ),
        targets=('python-standard',),
        run=run(
            10,
            20,
            python_check(
                'currentSourcePolicy',
                'repository.current-source-policy',
            ),
        ),
    ),
    GateSpec(
        name='acceptanceCaseMapping',
        description='检查验收用例表中的 ID 与自动化测试绑定完整一致。',
        trigger=changed(
            'docs/acceptance-cases/**/*.md',
            'tests/**/*.py',
            'tests/**/*.js',
            'tests/**/*.ts',
            'java/**/src/test/java/**/*.java',
            'scripts/gates/checks/repository/check_acceptance_case_mapping.py',
            'tests/checks/test_acceptance_case_mapping.py',
            'pyproject.toml',
        ),
        targets=(),
        run=run(
            15,
            30,
            python_check(
                'acceptanceCaseMapping',
                'repository.acceptance-case-mapping',
            ),
        ),
    ),
    GateSpec(
        name='testDataPolicy',
        description='确保测试输入数据受 Git 管理、可复现，并且不依赖个人电脑或真实 Session。',
        trigger=changed(
            'tests/**',
            'java/**/src/test/**',
            'scripts/gates/checks/repository/check_test_data_policy.py',
        ),
        targets=('python-standard', 'java-src'),
        run=run(
            15,
            30,
            python_check(
                'testDataPolicy',
                'repository.test-data-policy',
                '--repo-root',
                '{repo_root}',
            ),
        ),
    ),
    GateSpec(
        name='secretLikeContent',
        description='扫描仓库中的密钥、Token 与凭据形态内容。',
        trigger=changed(
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
            'scripts/gates/checks/privacy/check_secret_like_content.py',
        ),
        targets=('python-standard',),
        run=run(
            20,
            45,
            python_check(
                'secretLikeContent',
                'security.secret-like-content',
            ),
        ),
    ),
    GateSpec(
        name='languagePolicy',
        description='统一检查仓库政策文本与脚本注释符合中文维护规范。',
        trigger=changed(
            'AGENTS.md',
            'CLAUDE.md',
            'skills/**',
            '.agents/**',
            '.codex/**',
            '.claude/**',
            '.qoder/**',
            'harness/**',
            'openspec/changes/**',
            'scripts/**/*.py',
            'scripts/**/*.sh',
            'config/technical-terms.json',
        ),
        targets=('harness', 'python-standard', 'java-build'),
        run=run(
            18,
            35,
            python_check(
                'languagePolicy',
                'repository.language-policy',
            ),
            python_check(
                'scriptCommentLanguage',
                'source.comment-language',
                'scripts',
                '--policy',
                '{repo_root}/config/technical-terms.json',
            ),
        ),
    ),
    GateSpec(
        name='agentPolicy',
        description='统一检查 Agent 运行配置与维护文档政策。',
        trigger=changed(
            'AGENTS.md',
            'CLAUDE.md',
            '.agents/**',
            '.claude/**',
            '.codex/**',
            '.qoder/**',
            'skills/**',
            'harness/**',
            'scripts/harness/**/*.py',
            'scripts/harness/**/*.sh',
            'scripts/gates/checks/**/*.py',
            'scripts/gates/**/*.py',
        ),
        targets=('harness',),
        run=run(
            30,
            60,
            python_check(
                'agentRuntimePolicy',
                'agent.runtime-policy',
            ),
            python_check(
                'agentDocumentPolicy',
                'agent.document-policy',
            ),
        ),
    ),
    GateSpec(
        name='governanceStructure',
        description='统一验证 Skill registry、Harness 结构与 OpenSpec 布局。',
        trigger=changed(
            'harness/skill-registry.yaml',
            'skills/**',
            '.agents/skills/**',
            '.claude/skills/**',
            '.codex/skills/**',
            'scripts/gates/checks/agent/check_skill_registry.py',
            'harness/**',
            'scripts/harness/**/*.py',
            'openspec/**',
        ),
        targets=('harness',),
        run=run(
            24,
            45,
            python_check(
                'skillRegistry',
                'agent.skill-registry',
            ),
            command(
                'harnessStructure',
                '{python}',
                'scripts/harness/validate_harness_structure.py',
            ),
            command(
                'openspecLayout',
                '{python}',
                'scripts/openspec/validate_layout.py',
            ),
        ),
    ),
    GateSpec(
        name='webSourcePolicy',
        description='统一检查 Web 模板、脚本、静态资源与 CSS 源码政策。',
        trigger=changed(
            'java/web/src/main/resources/**',
            'java/tests/quality-gates/**',
            'config/web-quality-baselines.json',
            'tests/**/*.js',
            'scripts/**/*.js',
            'scripts/gates/executor.py',
            'tests/gates/test_executor.py',
        ),
        targets=('session-detail', 'python-standard', 'java-src'),
        run=run(
            90,
            180,
            java_rule('rawInnerhtml', 'raw-innerhtml'),
            java_rule('layoutInlineStyle', 'layout-inline-style'),
            java_rule('templateContract', 'template-contract'),
            java_rule('staticCssContract', 'static-resource-contract'),
            java_rule('cssOwnership', 'css-ownership'),
        ),
    ),
    GateSpec(
        name='webResourceTests',
        description='运行 Java Web 模板、CSS 与 JavaScript 的资源契约测试。',
        trigger=changed(
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
        ),
        targets=('session-detail', 'java-src'),
        run=run(
            60,
            180,
            gradle_task(
                'webResourceTests',
                ':java:web:test',
            ),
        ),
    ),
    GateSpec(
        name='browserLayout',
        description='用 Playwright 验证主要页面、布局与视觉壳层契约。',
        trigger=changed(
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'tests/playwright/**',
        ),
        targets=('session-detail',),
        run=run(
            90,
            240,
            playwright(
                'browserLayout',
                (
                    'ui-contract.spec.ts',
                    'main-pages-visual.spec.ts',
                    'session-detail-layout',
                    'shell-states',
                    'dashboard-chart-coordinates',
                ),
                '--workers={playwright_workers}',
            ),
        ),
    ),
    GateSpec(
        name='browserInteraction',
        description='用 Playwright 验证 Session、列表与迁移页面交互。',
        trigger=changed(
            'java/web/src/main/resources/templates/**',
            'java/web/src/main/resources/static/**',
            'tests/playwright/**',
        ),
        targets=('session-detail',),
        run=run(
            90,
            240,
            playwright(
                'browserInteraction',
                (
                    'session-detail.spec.js',
                    'session-detail-migrated-gates.spec.js',
                    'sessions-list.spec.js',
                ),
                '--grep-invert',
                '100 轮',
                '--workers={playwright_workers}',
            ),
        ),
    ),
    GateSpec(
        name='javaCheck',
        description='运行 Java 编译、测试和标准源码规则。',
        trigger=changed(
            'java/**/src/main/java/**/*.java',
            'java/**/src/test/java/**/*.java',
            'java/**/src/main/kotlin/**/*.kt',
            'java/**/src/test/kotlin/**/*.kt',
            '**/*.java',
            'config/architecture/java-modules.yaml',
            'config/technical-terms.json',
            'gradle/build-logic/**',
            'gradle/**',
            'build.gradle.kts',
            'settings.gradle.kts',
            'java/**/build.gradle.kts',
            'gradle.properties',
            'gradlew',
            'gradlew.bat',
            '*.lockfile',
        ),
        targets=('java-src', 'java-build'),
        run=run(
            240,
            600,
            gradle_task(
                'javaCheck',
                'check',
                '--parallel',
                '--build-cache',
            ),
        ),
    ),
    GateSpec(
        name='javaReusePolicy',
        description='使用 CPD 检查 Java 生产源码中的重复实现。',
        trigger=changed(
            'java/**/src/main/java/**/*.java',
            'config/reuse-policy/**',
            'java/**/build.gradle.kts',
            'settings.gradle.kts',
            'build.gradle.kts',
        ),
        targets=('java-src', 'java-build'),
        run=run(
            180,
            600,
            gradle_task(
                'reuseStandardCpd',
                'reuseStandardCpd',
            ),
        ),
    ),
    GateSpec(
        name='scanScriptSmoke',
        description='验证 session-browser scan 命令与发行 CLI 的进程级契约。',
        trigger=changed(
            'scripts/session-browser.sh',
            'java/app-cli/**',
            'java/scan-engine/**',
            'java/sources/**',
            'java/index-sqlite/**',
            'scripts/gates/checks/**',
            'tests/script_commands/**',
        ),
        targets=('scan-script-smoke',),
        run=run(
            90,
            180,
            scan_smoke(
                'scanScriptSmoke',
                ('tests/script_commands/test_session_browser_scan_smoke.py',),
                (':java:app-cli:installDist',),
                '-q',
                '-W',
                'error',
            ),
        ),
    ),
    GateSpec(
        name='sessionSamples',
        description='用合成 Session 样本验证解析、标准化与契约集成。',
        trigger=changed(
            'tests/fixtures/session_samples/**',
            'java/core-domain/src/main/java/com/feipi/session/browser/domain/normalized/**',
            'java/sources/**',
            'java/normalization-engine/**',
            'java/artifact-normalized/**',
            'java/tests/contracts/src/test/java/com/feipi/session/browser/contracttest/sample/**',
        ),
        targets=('scan-script-smoke',),
        run=run(
            90,
            240,
            gradle_task(
                'sessionSamples',
                ':java:tests:contracts:sampleIntegrationTest',
            ),
        ),
    ),
)


CATALOG = GateCatalog(TARGETS, GATES)
