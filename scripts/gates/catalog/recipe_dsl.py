"""负责提供声明 Gate recipe 的最小类型化 DSL；不负责执行 RecipeStep。

由 Catalog 各领域声明文件调用。"""

from __future__ import annotations

from scripts.gates.catalog.gate_contracts import (
    DurationExpectations,
    GateRecipe,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
)

# 这些入口直接决定 Java/Playwright 命令和环境；领域审计、报告和 doctor 不是其输入。
PRODUCT_EXECUTION_PATHS = (
    'scripts/session-browser.sh',
    'scripts/harness/java_env.sh',
    'scripts/harness/python_env.py',
    'scripts/gates/*.py',
    'scripts/gates/catalog/**',
    'scripts/gates/config/**',
    'scripts/gates/execution/**',
    'scripts/gates/planning/**',
)


# settings.gradle.kts 将 installDist 的应用模块放在 java 的一级子目录。
# 深层测试项目的构建不进入运行分发；根构建和 build-logic 仍共享。
JAVA_RUNTIME_BUILD_INPUTS = (
    'java/*/build.gradle.kts',
    'java/build.gradle.kts',
    'java/settings.gradle.kts',
    'java/gradle.properties',
    'java/gradle/**',
    'java/gradlew*',
    'java/*.lockfile',
)


def changed(*paths: str) -> GateTrigger:
    """声明只在 changed path 命中时自动选择的 Gate。"""

    return GateTrigger(paths)


def recipe(incremental: int, full: int, *steps: RecipeStep) -> GateRecipe:
    """绑定唯一 RecipeStep 列表与两种非阻断时效目标。"""

    return GateRecipe(DurationExpectations(incremental, full), steps)


def command(
    name: str,
    *argv: str,
    required_paths: tuple[str, ...] = (),
    append_globs: tuple[str, ...] = (),
) -> RecipeStep:
    """声明一个标准外部命令步骤。"""

    return RecipeStep(
        name,
        RecipeStepKind.COMMAND,
        argv=argv,
        required_paths=required_paths,
        append_globs=append_globs,
    )


def python_check(name: str, check_id: str, *args: str) -> RecipeStep:
    """声明一个由 Python Check registry 执行的领域步骤。"""

    return RecipeStep(
        name,
        RecipeStepKind.PYTHON_CHECK,
        check_id=check_id,
        args=args,
    )


def gradle_task(name: str, task: str, *args: str) -> RecipeStep:
    """声明只拥有一个 Gradle task 的步骤。"""

    return RecipeStep(name, RecipeStepKind.GRADLE_TASK, tasks=(task,), args=args)


def java_rule(name: str, *rules: str) -> RecipeStep:
    """声明由同一 Java runner 执行的源码规则集合。"""

    return RecipeStep(name, RecipeStepKind.JAVA_RULE, rules=rules)


def playwright(name: str) -> RecipeStep:
    """声明由 Playwright 原生完整发现的 suite。"""

    return RecipeStep(name, RecipeStepKind.PLAYWRIGHT)


def scan_smoke(
    name: str,
    tests: tuple[str, ...],
    *args: str,
) -> RecipeStep:
    """声明由公开 launcher 自行准备发行目录的 scan smoke 步骤。"""

    return RecipeStep(
        name,
        RecipeStepKind.SCAN_SMOKE,
        tests=tests,
        args=args,
    )
