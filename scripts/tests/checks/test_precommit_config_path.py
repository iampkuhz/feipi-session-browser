"""验证下沉配置的显式安装路径，不触碰用户工作树 hook。"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_ruff_hooks_select_nested_config() -> None:
    config = yaml.safe_load((ROOT / 'scripts/.pre-commit-config.yaml').read_text())
    hooks = {hook['id']: hook for repo in config['repos'] for hook in repo['hooks']}
    for name in ('ruff-format', 'ruff'):
        args = hooks[name]['args']
        assert args[args.index('--config') + 1] == 'scripts/pyproject.toml'
    assert '--fix' in hooks['ruff']['args']


def test_nested_precommit_config_installs_in_synthetic_repository(tmp_path: Path) -> None:
    config = tmp_path / 'scripts/.pre-commit-config.yaml'
    config.parent.mkdir()
    config.write_text(
        'repos:\n- repo: local\n  hooks:\n'
        '  - id: nested-path\n    name: nested-path\n'
        '    entry: echo nested-config-ok\n    language: system\n    always_run: true\n'
    )
    env = {
        **os.environ,
        'PRE_COMMIT_HOME': str(tmp_path / 'cache'),
        'GIT_CONFIG_GLOBAL': os.devnull,
        'GIT_CONFIG_NOSYSTEM': '1',
    }
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True, env=env)
    installed = subprocess.run(
        [
            sys.executable,
            '-m',
            'pre_commit',
            'install',
            '--config',
            'scripts/.pre-commit-config.yaml',
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert 'installed' in installed.stdout
    hook = tmp_path / '.git/hooks/pre-commit'
    assert '--config=scripts/.pre-commit-config.yaml' in hook.read_text()
    result = subprocess.run(
        [str(hook)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert 'Passed' in result.stdout
