"""测试 Python 环境和依赖锁契约."""

from pathlib import Path

import pytest
import tomllib
from scripts.gates import executor as gate_executor
from scripts.harness import python_env

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_project(root: Path, *, dev_extra: str = '') -> None:
    (root / 'pyproject.toml').write_text(
        '\n'.join(
            [
                '[project]',
                'requires-python = ">=3.12,<3.13"',
                'dependencies = ["jinja2", "markdown-it-py"]',
                '',
                '[project.optional-dependencies]',
                'dev = ["pytest", "pytest-xdist", "playwright"' + dev_extra + ']',
                '',
            ]
        ),
        encoding='utf-8',
    )
    (root / 'requirements.txt').write_text('jinja2\nmarkdown-it-py\n', encoding='utf-8')
    (root / 'requirements-dev.txt').write_text(
        '-r requirements.txt\npytest\npytest-xdist\nplaywright\n',
        encoding='utf-8',
    )
    (root / 'requirements.lock').write_text(
        'jinja2==3.1.6\nmarkdown-it-py==4.0.0\n',
        encoding='utf-8',
    )
    (root / 'requirements-dev.lock').write_text(
        'jinja2==3.1.6\nmarkdown-it-py==4.0.0\npytest==9.0.3\npytest-xdist==3.8.0\nplaywright==1.59.0\n',
        encoding='utf-8',
    )
    (root / 'uv.lock').write_text(
        'version = 1\nrequires-python = ">=3.12,<3.13"\n', encoding='utf-8'
    )
    (root / '.python-version').write_text('3.12.11\n', encoding='utf-8')


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_repository_pyproject_is_virtual_dev_tools_project():
    """Python 产品退役后，uv 不得再构建或安装当前仓库。"""
    config = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))

    assert 'build-system' not in config
    assert 'setuptools' not in config.get('tool', {})
    assert config['project']['name'] == 'feipi-session-browser-dev-tools'
    assert config['tool']['uv']['package'] is False
    assert config['tool']['pytest']['ini_options']['pythonpath'] == ['.']


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_resolve_python_order_prefers_env_then_venv_then_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    venv_python = tmp_path / '.venv' / 'bin' / 'python'
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text('', encoding='utf-8')
    selected: list[str] = []

    def fake_supports(candidate: str) -> bool:
        selected.append(candidate)
        return str(candidate) == str(venv_python)

    monkeypatch.delenv('SESSION_BROWSER_PYTHON', raising=False)
    monkeypatch.delenv('SESSION_BROWSER_VENV_DIR', raising=False)
    monkeypatch.setattr(python_env, '_supports_python_version', fake_supports)

    assert python_env.resolve_python(tmp_path) == str(venv_python)
    assert selected[0] == str(venv_python)

    monkeypatch.setenv('SESSION_BROWSER_PYTHON', '/tmp/project-python')
    monkeypatch.setattr(
        python_env, '_supports_python_version', lambda candidate: candidate == '/tmp/project-python'
    )

    assert python_env.resolve_python(tmp_path) == '/tmp/project-python'


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_lock_check_requires_requirements_pyproject_and_locks_to_match(tmp_path: Path):
    _write_project(tmp_path)

    assert python_env.check_locks(tmp_path) == []

    (tmp_path / 'requirements.lock').write_text('jinja2==3.1.6\n', encoding='utf-8')

    problems = python_env.check_locks(tmp_path)
    assert any('requirements.lock 缺少: markdown-it-py' in problem for problem in problems)


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_lock_check_rejects_unpinned_lock_entries(tmp_path: Path):
    _write_project(tmp_path)
    (tmp_path / 'requirements-dev.lock').write_text(
        'jinja2==3.1.6\nmarkdown-it-py==4.0.0\npytest\npytest-xdist==3.8.0\nplaywright==1.59.0\n',
        encoding='utf-8',
    )

    problems = python_env.check_locks(tmp_path)
    assert any('requirements-dev.lock 未固定版本' in problem for problem in problems)


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_lock_check_requires_python_312_contract(tmp_path: Path):
    _write_project(tmp_path)
    (tmp_path / '.python-version').write_text('3.13.0\n', encoding='utf-8')

    problems = python_env.check_locks(tmp_path)

    assert any('.python-version 必须锁定到 Python 3.12 patch' in problem for problem in problems)


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_lock_check_accepts_uv_minor_lock_equivalent(tmp_path: Path):
    _write_project(tmp_path)
    (tmp_path / 'uv.lock').write_text(
        'version = 1\nrequires-python = "==3.12.*"\n', encoding='utf-8'
    )

    assert python_env.check_locks(tmp_path) == []


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_quality_gate_project_python_uses_shared_resolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    gate_executor._project_python_cached.cache_clear()
    calls: list[Path] = []

    def fake_resolve(repo_root: Path) -> str:
        calls.append(repo_root)
        return '/tmp/shared-python'

    monkeypatch.setattr(gate_executor, 'resolve_python', fake_resolve)

    assert gate_executor._project_python(tmp_path) == '/tmp/shared-python'
    assert calls == [tmp_path]


@pytest.mark.contract_case('HOOK-HARNESS-010')
def test_quality_gate_dev_python_requires_pytest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """开发 Gate 不得选择缺少 pytest 的仓库虚拟环境。"""
    gate_executor._project_python_cached.cache_clear()
    monkeypatch.setattr(gate_executor, 'resolve_python', lambda _root: '/tmp/runtime-python')
    monkeypatch.setattr(
        gate_executor,
        '_python_candidates',
        lambda _root: ['/tmp/runtime-python', '/tmp/dev-python'],
    )
    monkeypatch.setattr(
        gate_executor,
        '_python_supports_modules',
        lambda executable, _root, modules: (
            executable == '/tmp/dev-python' and modules == ('pytest',)
        ),
    )

    assert gate_executor._project_python(tmp_path, dev=True) == '/tmp/dev-python'
