"""负责提供声明 Gate recipe 的最小类型化 DSL；不负责执行 RecipeStep。

由 Catalog 各领域声明文件调用。"""

from __future__ import annotations

from scripts.gates.catalog.gate_contracts import (
    DurationExpectations,
    GateRecipe,
    GateTrigger,
    RecipeStep,
    RecipeStepKind,
    TriggerMode,
)


def changed(*paths: str) -> GateTrigger:
    """声明只在 changed path 命中时自动选择的 Gate。"""

    return GateTrigger(TriggerMode.CHANGED, paths)


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


def python_check(name: str, check_id: str, *args: str, runtime: str = 'system') -> RecipeStep:
    """声明一个由 Python Check registry 执行的领域步骤。"""

    return RecipeStep(
        name,
        RecipeStepKind.PYTHON_CHECK,
        check_id=check_id,
        runtime=runtime,
        args=args,
    )


def gradle_task(name: str, task: str, *args: str) -> RecipeStep:
    """声明只拥有一个 Gradle task 的步骤。"""

    return RecipeStep(name, RecipeStepKind.GRADLE_TASK, tasks=(task,), args=args)


def java_rule(name: str, rule: str) -> RecipeStep:
    """声明只拥有一个 Java 源码规则的步骤。"""

    return RecipeStep(name, RecipeStepKind.JAVA_RULE, rules=(rule,))


def playwright(name: str, tests: tuple[str, ...], *args: str) -> RecipeStep:
    """声明固定 Playwright suite 的步骤。"""

    return RecipeStep(name, RecipeStepKind.PLAYWRIGHT, tests=tests, args=args)


def scan_smoke(
    name: str,
    tests: tuple[str, ...],
    prerequisite_tasks: tuple[str, ...],
    *args: str,
) -> RecipeStep:
    """声明需要准备 Java distribution 的 scan smoke 步骤。"""

    return RecipeStep(
        name,
        RecipeStepKind.SCAN_SMOKE,
        tests=tests,
        prerequisite_tasks=prerequisite_tasks,
        args=args,
    )
