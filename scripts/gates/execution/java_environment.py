"""负责在执行阶段解析共享 JDK 环境；不负责计划选择，由 Gate 执行编排器调用。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.gates.execution.command_adapter import sanitized_environment

if TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts.gates.planning.plan_compiler import CommandInvocation


def resolve_java_environment(
    repo_root: Path, overrides: Mapping[str, str | None]
) -> dict[str, str | None]:
    """为本次执行的所有子进程冻结有效 JDK 目录与 PATH。"""
    environment = sanitized_environment(overrides)
    try:
        result = subprocess.run(
            ['bash', str(repo_root / 'scripts/harness/java_env.sh')],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'JDK 25 discovery failed: {exc}') from exc
    if result.returncode:
        raise RuntimeError(f'JDK 25 discovery failed: {result.stderr.strip()[:2000]}')
    home = result.stdout.strip()
    if not home or '\n' in home:
        raise RuntimeError('JDK 25 discovery returned an invalid home')
    return {**overrides, 'JAVA_HOME': home, 'PATH': f'{home}/bin:{environment.get("PATH", "")}'}


def requires_java(invocations: tuple[CommandInvocation, ...]) -> bool:
    """识别需要 Java 的消费者，包括启动产品服务的浏览器测试。"""
    return any(
        item.kind in {'gradle-task', 'java-rule', 'gradle-prerequisite', 'scan-smoke', 'playwright'}
        or any(
            Path(arg).name in {'gradlew', 'gradlew.bat', 'java', 'javac', 'session-browser.sh'}
            for arg in item.argv[:2]
        )
        for item in invocations
    )
