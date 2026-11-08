"""Shared JDK discovery is execution-only and preserves explicit configuration."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.gates.execution.java_environment import requires_java, resolve_java_environment
from scripts.gates.planning.plan_compiler import CommandInvocation
from scripts.tests.script_commands.test_java_environment import (
    REPO_ROOT,
    _create_fake_jdk,
    _minimal_env,
)


def test_shared_discovery_freezes_explicit_jdk(tmp_path: Path) -> None:
    jdk = tmp_path / 'jdk with spaces'
    _create_fake_jdk(jdk)
    env = _minimal_env(tmp_path)
    env['JAVA_HOME'] = str(jdk)
    with patch('os.environ', env):
        result = resolve_java_environment(REPO_ROOT, {'EXTRA': 'retained'})
    assert result['JAVA_HOME'] == str(jdk)
    assert result['PATH'] == f'{jdk}/bin:{env["PATH"]}'
    assert result['EXTRA'] == 'retained'


def test_invalid_explicit_home_does_not_fall_back(tmp_path: Path) -> None:
    jdk = tmp_path / 'valid'
    _create_fake_jdk(jdk)
    env = _minimal_env(tmp_path)
    env.update(JAVA_HOME=str(tmp_path / 'invalid'), PATH=f'{jdk}/bin:{env["PATH"]}')
    with patch('os.environ', env), pytest.raises(RuntimeError, match='JAVA_HOME'):
        resolve_java_environment(REPO_ROOT, {})


def test_discovery_sanitizes_provider_environment() -> None:
    result = subprocess.CompletedProcess([], 0, '/jdk\n', '')
    with (
        patch.dict('os.environ', {'CODEX_PRIVATE': 'secret'}),
        patch(
            'scripts.gates.execution.java_environment.subprocess.run', return_value=result
        ) as run,
    ):
        resolve_java_environment(REPO_ROOT, {})
    assert 'CODEX_PRIVATE' not in run.call_args.kwargs['env']


@pytest.mark.parametrize(
    'kind,argv,expected',
    [
        ('command', ('python3', 'check.py'), False),
        ('command', ('./java/gradlew', 'check'), True),
        ('gradle-task', ('wrapper',), True),
        ('java-rule', ('wrapper',), True),
        ('scan-smoke', ('python3', '-m', 'pytest'), True),
        ('playwright', ('python3', '-m', 'pytest'), True),
    ],
)
def test_only_java_consumers_require_resolution(kind, argv, expected) -> None:
    invocation = CommandInvocation('id', kind, argv, (), 'gate', 'step')
    assert requires_java((invocation,)) is expected
