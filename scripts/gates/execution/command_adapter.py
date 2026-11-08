"""负责把 Catalog RecipeStep 适配为冻结的 CommandInvocation；不负责启动进程。

由 Planning 编译计划和 Maintenance 健康审计调用。"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.gates.catalog.gate_contracts import ExecutionMode, RecipeStepKind
from scripts.harness.python_env import resolve_python, tool_config_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts.gates.catalog.gate_contracts import Gate, RecipeStep
    from scripts.gates.planning.plan_compiler import CommandInvocation

PROVIDER_ENV_PREFIXES = ('CODEX_', 'QODER_', 'CLAUDE_')
JAVA_QUALITY_RULES_PROPERTY = '-PfeipiJavaQualityRules='


def sanitized_environment(
    overrides: Mapping[str, str | None] | None = None,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """合并环境覆盖，并剔除 provider 私有变量。"""

    source = os.environ if base is None else base
    result = {str(key): str(value) for key, value in source.items()}
    for key, value in (overrides or {}).items():
        if value is None:
            result.pop(str(key), None)
        else:
            result[str(key)] = str(value)
    for key in tuple(result):
        if key.startswith(PROVIDER_ENV_PREFIXES):
            result.pop(key, None)
    return result


@lru_cache(maxsize=8)
def _project_python(repo_root: Path) -> str:
    return resolve_python(repo_root)


def _expand(argument: str, repo_root: Path) -> str:
    values = {
        'repo_root': str(repo_root),
        'tool_config': str(tool_config_path(repo_root)),
    }
    # 不为无关占位符探测 Python 环境。
    if '{python}' in argument:
        values['python'] = _project_python(repo_root)
    return argument.format_map(values)


def _repository_files(repo_root: Path, patterns: tuple[str, ...]) -> tuple[str, ...]:
    files: list[str] = []
    for pattern in patterns:
        files.extend(
            path.relative_to(repo_root).as_posix()
            for path in sorted(repo_root.glob(pattern))
            if path.is_file()
        )
    return tuple(dict.fromkeys(files))


def _framework_test_paths(repo_root: Path, changed_files: tuple[str, ...]) -> tuple[str, ...]:
    """空结果保留完整发现；目录选择同时包含新增和同组回归。"""
    suites: set[str] = set()
    for path in changed_files:
        parts = Path(path).parts
        if (
            parts[:2] == ('scripts', 'tests')
            and len(parts) >= 4
            and parts[2] in {'checks', 'gates', 'harness', 'misc', 'quality'}
            and parts[-1].startswith('test_')
            and path.endswith('.py')
        ):
            suites.add(f'scripts/tests/{parts[2]}')
        elif parts[:3] == ('scripts', 'gates', 'presentation') and path.endswith('.py'):
            suites.update(('scripts/tests/gates', 'root'))
        elif (
            parts[:3] == ('scripts', 'gates', 'checks')
            and len(parts) >= 5
            and parts[3] in {'agent', 'privacy', 'repository', 'source'}
            and path.endswith('.py')
        ):
            suites.update(('scripts/tests/checks', 'scripts/tests/gates', 'root'))
        else:
            return ()
    root_tests = (
        _repository_files(repo_root, ('scripts/tests/test_*.py',)) if 'root' in suites else ()
    )
    suites.discard('root')
    if not all((repo_root / suite).is_dir() for suite in suites):
        return ()
    return (*sorted(suites), *root_tests)


def _gradle_command_prefix(repo_root: Path) -> tuple[str, ...]:
    """选取平台 wrapper 并显式冻结构建根；缺少 wrapper 时不生成进程。"""
    build_root = repo_root / 'java'
    wrapper = build_root / 'gradlew'
    return (str(wrapper), '-p', str(build_root)) if wrapper.is_file() else ()


def _step_command(step: RecipeStep, repo_root: Path) -> tuple[str, ...]:
    kind = step.kind
    if kind is RecipeStepKind.COMMAND:
        if not step.argv or any(not (repo_root / path).exists() for path in step.required_paths):
            return ()
        appended = _repository_files(repo_root, step.append_globs)
        if step.append_globs and not appended:
            return ()
        return (*(_expand(value, repo_root) for value in step.argv), *appended)
    if kind is RecipeStepKind.PYTHON_CHECK:
        if not step.check_id:
            return ()
        return (
            _project_python(repo_root),
            '-m',
            'scripts.gates.checks',
            step.check_id,
            *(_expand(value, repo_root) for value in step.args),
        )
    if kind in {RecipeStepKind.GRADLE_TASK, RecipeStepKind.JAVA_RULE}:
        gradle_prefix = _gradle_command_prefix(repo_root)
        if not gradle_prefix:
            return ()
        tasks = step.tasks or (':java:tests:quality-gates:runJavaQualityGates',)
        rules = (f'{JAVA_QUALITY_RULES_PROPERTY}{",".join(step.rules)}',) if step.rules else ()
        return (*gradle_prefix, *tasks, *rules, *step.args, '--console=plain')
    if kind is RecipeStepKind.PLAYWRIGHT:
        return ('npm', '--prefix', 'java/tests/playwright', 'test')
    if kind is RecipeStepKind.SCAN_SMOKE:
        return (
            _project_python(repo_root),
            '-m',
            'pytest',
            '-c',
            str(tool_config_path(repo_root)),
            '--rootdir',
            str(repo_root),
            *step.args,
            *step.tests,
        )
    raise ValueError(f'unknown RecipeStepKind: {kind}')


def _request_environment(
    mode: ExecutionMode | str,
    changed_files: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    selected_mode = ExecutionMode(mode)
    values = {'QUALITY_EXECUTION_MODE': selected_mode.value}
    if selected_mode is ExecutionMode.INCREMENTAL:
        values['QUALITY_CHANGED_FILES'] = json.dumps(changed_files, ensure_ascii=False)
    return tuple(sorted(values.items()))


def adapt_recipe_step(
    gate: Gate,
    step: RecipeStep,
    repo_root: Path | str,
    *,
    mode: ExecutionMode | str,
    changed_files: tuple[str, ...] = (),
) -> tuple[CommandInvocation, ...]:
    """把一个 RecipeStep 冻结为真实进程声明。"""

    from scripts.gates.planning.plan_compiler import CommandInvocation

    root = Path(repo_root).resolve()
    environment = _request_environment(mode, changed_files)
    prefix = f'{gate.name}:{step.name}'
    command = _step_command(step, root)
    if command and gate.name == 'gateFrameworkTests' and mode == ExecutionMode.INCREMENTAL:
        if paths := _framework_test_paths(root, changed_files):
            command = (*command[:-1], *paths)
    if not command:
        return ()
    return (
        CommandInvocation(
            f'{prefix}:run', step.kind.value, command, environment, gate.name, step.name
        ),
    )
