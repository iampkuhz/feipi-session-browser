"""用合成文件执行开发表中的原生 Python 静态反馈命令。"""

import re
import shlex
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _feedback_command() -> str:
    text = (REPO_ROOT / 'docs/development/README.md').read_text(encoding='utf-8')
    section = re.search(r'### Python 静态反馈\n(.*?)(?=\n## |\Z)', text, re.DOTALL)
    if section:
        return re.search(r'```bash\n(.*?)\n```', section[1], re.DOTALL)[1]
    # 旧开发表只有 lint 命令；保留它以证明格式缺陷确实会漏过。
    return re.search(r'`([^`]*ruff check[^`]*<path>)`', text)[1]


def _run_feedback(path: Path) -> subprocess.CompletedProcess[str]:
    command = _feedback_command().replace('<path>', shlex.quote(str(path)))
    return subprocess.run(
        ['bash', '-c', command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    'source,diagnostic', [('value=1\n', 'Would reformat'), ('import os\n', 'F401')]
)
def test_static_feedback_rejects_format_and_lint_before_tests(
    tmp_path: Path, source: str, diagnostic: str
):
    probe = tmp_path / 'probe with spaces.py'
    probe.write_text(source, encoding='utf-8')
    result = _run_feedback(probe)
    assert result.returncode != 0, result.stdout + result.stderr
    assert diagnostic in result.stdout + result.stderr
    # 反馈只读，不自动格式化或修复待交付源码。
    assert probe.read_text(encoding='utf-8') == source

    (tmp_path / 'unrelated.py').write_text('import os\nvalue=1\n', encoding='utf-8')
    probe.write_text('value = 1\n', encoding='utf-8')
    repaired = _run_feedback(probe)
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr


def test_local_feedback_does_not_collect_unrelated_dirty_git_paths(tmp_path: Path):
    def git(*arguments):
        return subprocess.run(
            ['git', *arguments], cwd=tmp_path, capture_output=True, text=True, check=True
        ).stdout

    git('init', '-q')
    unrelated = tmp_path / 'unrelated.py'
    unrelated.write_text('value = 1\n', encoding='utf-8')
    git('add', 'unrelated.py')
    git(
        '-c',
        'user.name=Synthetic',
        '-c',
        'user.email=test@example.invalid',
        'commit',
        '-qm',
        'base',
    )
    unrelated.write_text('import os\nvalue=1\n', encoding='utf-8')
    probe = tmp_path / 'probe with spaces.py'
    probe.write_text('value = 2\n', encoding='utf-8')
    before = git('status', '--porcelain')
    assert ' M unrelated.py' in before and '?? "probe with spaces.py"' in before
    # 仅将受管工具/配置定位到真仓库，原开发表的路径选择和 shell 语义不变。
    command = (
        _feedback_command()
        .replace(
            '.local/python/venv/bin/ruff',
            shlex.quote(str(REPO_ROOT / '.local/python/venv/bin/ruff')),
        )
        .replace('scripts/pyproject.toml', shlex.quote(str(REPO_ROOT / 'scripts/pyproject.toml')))
        .replace('<path>', shlex.quote(str(probe)))
    )
    result = subprocess.run(
        ['bash', '-c', command], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert git('status', '--porcelain') == before
    assert unrelated.read_text(encoding='utf-8') == 'import os\nvalue=1\n'
