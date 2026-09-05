"""负责把 Catalog RecipeStep 适配为冻结的 CommandInvocation；不负责启动进程。

由 Planning 编译计划和 Maintenance 健康审计调用。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.gates.catalog.gate_contracts import ExecutionMode, RecipeStepKind
from scripts.harness.python_env import project_venv_dir, resolve_python, tool_config_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts.gates.catalog.gate_contracts import Gate, RecipeStep
    from scripts.gates.planning.plan_compiler import CommandInvocation

PROVIDER_ENV_PREFIXES = ('CODEX_', 'QODER_', 'CLAUDE_')
PLAYWRIGHT_MIN_WORKERS = 8
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


def _python_candidates(repo_root: Path) -> tuple[str, ...]:
    candidates = [
        os.environ.get('SESSION_BROWSER_PYTHON', ''),
        str(project_venv_dir(repo_root) / 'bin' / 'python'),
        shutil.which('python') or '',
        shutil.which('python3') or '',
        sys.executable,
    ]
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def _supports_modules(executable: str, repo_root: Path, modules: tuple[str, ...]) -> bool:
    if shutil.which(executable) is None and not Path(executable).is_file():
        return False
    probe = (
        'import importlib.util,sys;'
        'sys.exit(0 if all(importlib.util.find_spec(n) for n in sys.argv[1:]) else 1)'
    )
    try:
        result = subprocess.run(
            [executable, '-c', probe, *modules],
            cwd=repo_root,
            env=sanitized_environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


@lru_cache(maxsize=8)
def _project_python_cached(repo_root: str, modules: tuple[str, ...]) -> str:
    """缓存满足指定模块依赖的项目 Python 路径，避免重复探测解释器。"""
    root = Path(repo_root)
    resolved = resolve_python(root)
    if not modules or _supports_modules(resolved, root, modules):
        return resolved
    for candidate in _python_candidates(root):
        if _supports_modules(candidate, root, modules):
            return candidate
    raise RuntimeError(f'缺少包含开发依赖的 Python: {", ".join(modules)}')


def _project_python(repo_root: Path, *, dev: bool = False) -> str:
    return _project_python_cached(str(repo_root.resolve()), ('pytest',) if dev else ())


def _playwright_workers() -> int:
    raw = (
        os.environ.get('SESSION_BROWSER_PLAYWRIGHT_WORKERS')
        or os.environ.get('PLAYWRIGHT_WORKERS')
        or ''
    ).strip()
    try:
        return max(PLAYWRIGHT_MIN_WORKERS, int(raw)) if raw else PLAYWRIGHT_MIN_WORKERS
    except ValueError:
        return PLAYWRIGHT_MIN_WORKERS


def _expand(argument: str, repo_root: Path) -> str:
    return argument.format_map(
        {
            'python': _project_python(repo_root),
            'dev_python': _project_python(repo_root, dev=True),
            'repo_root': str(repo_root),
            'tool_config': str(tool_config_path(repo_root)),
            'playwright_workers': str(_playwright_workers()),
        }
    )


def _repository_files(repo_root: Path, patterns: tuple[str, ...]) -> tuple[str, ...]:
    files: list[str] = []
    for pattern in patterns:
        files.extend(
            path.relative_to(repo_root).as_posix()
            for path in sorted(repo_root.glob(pattern))
            if path.is_file()
        )
    return tuple(dict.fromkeys(files))


def _gradle_command_prefix(repo_root: Path) -> tuple[str, ...]:
    """选取平台 wrapper 并显式冻结构建根；缺少 wrapper 时不生成进程。"""
    build_root = repo_root / 'java'
    wrapper = build_root / ('gradlew.bat' if sys.platform == 'win32' else 'gradlew')
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
            _project_python(repo_root, dev=step.runtime == 'dev'),
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
        return (
            'npm',
            '--prefix',
            'java/tests/playwright',
            'test',
            '--',
            *step.tests,
            *(_expand(value, repo_root) for value in step.args),
        )
    if kind is RecipeStepKind.SCAN_SMOKE:
        return (
            _project_python(repo_root, dev=True),
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
    *,
    base_url: str | None,
    playwright: bool,
) -> tuple[tuple[str, str], ...]:
    selected_mode = ExecutionMode(mode)
    values = {'QUALITY_EXECUTION_MODE': selected_mode.value}
    if selected_mode is ExecutionMode.INCREMENTAL:
        values['QUALITY_CHANGED_FILES'] = json.dumps(changed_files, ensure_ascii=False)
    if playwright and base_url:
        values.update(
            {
                'BASE_URL': base_url,
                'PW_SESSION_URL': f'{base_url}/sessions/claude_code/hifi-viz-session-001',
                'PW_LONG_SESSION_URL': f'{base_url}/sessions/claude_code/long-session-001',
                'SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER': '1',
            }
        )
    return tuple(sorted(values.items()))


def adapt_recipe_step(
    gate: Gate,
    step: RecipeStep,
    repo_root: Path | str,
    *,
    mode: ExecutionMode | str,
    changed_files: tuple[str, ...] = (),
    base_url: str | None = None,
) -> tuple[CommandInvocation, ...]:
    """把一个 RecipeStep 冻结为一或多个真实进程声明。"""

    from scripts.gates.planning.plan_compiler import CommandInvocation

    root = Path(repo_root).resolve()
    environment = _request_environment(
        mode,
        changed_files,
        base_url=base_url,
        playwright=step.kind is RecipeStepKind.PLAYWRIGHT,
    )
    prefix = f'{gate.name}:{step.name}'
    command = _step_command(step, root)
    if step.kind is RecipeStepKind.SCAN_SMOKE:
        gradle_prefix = _gradle_command_prefix(root)
        prerequisite = (
            (*gradle_prefix, *step.prerequisite_tasks, '--console=plain')
            if gradle_prefix and step.prerequisite_tasks
            else ()
        )
        if not prerequisite or not command:
            return ()
        return (
            CommandInvocation(
                f'{prefix}:prerequisite',
                'gradle-prerequisite',
                prerequisite,
                environment,
                gate.name,
                step.name,
            ),
            CommandInvocation(
                f'{prefix}:run',
                step.kind.value,
                command,
                environment,
                gate.name,
                step.name,
            ),
        )
    if not command:
        return ()
    return (
        CommandInvocation(
            f'{prefix}:run', step.kind.value, command, environment, gate.name, step.name
        ),
    )
