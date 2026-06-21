"""测试 Python 环境和依赖锁契约."""

from pathlib import Path

import pytest
from scripts.harness import python_env
from scripts.quality import run_quality_gate


def _write_project(root: Path, *, dev_extra: str = '') -> None:
    (root / 'pyproject.toml').write_text(
        '\n'.join(
            [
                '[project]',
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
def test_quality_gate_project_python_uses_shared_resolver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    run_quality_gate._project_python_cached.cache_clear()
    calls: list[Path] = []

    def fake_resolve(repo_root: Path) -> str:
        calls.append(repo_root)
        return '/tmp/shared-python'

    monkeypatch.setattr(run_quality_gate, 'resolve_python', fake_resolve)

    assert run_quality_gate._project_python(tmp_path) == '/tmp/shared-python'
    assert calls == [tmp_path]
