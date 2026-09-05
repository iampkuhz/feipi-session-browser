"""固定受控顶层布局；本地 ignored 数据不属于 GitHub 展示结构。"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ROOT_DIRECTORIES = {
    '.agents',
    '.claude',
    '.codex',
    '.github',
    '.qoder',
    'docs',
    'harness',
    'java',
    'openspec',
    'scripts',
    'skills',
}
ROOT_FILES = {'.gitignore', 'AGENTS.md', 'README.md'}
OLD_ENTRIES = (
    'tests',
    'config',
    'gradle',
    'CLAUDE.md',
    'VERSION',
    'build.gradle.kts',
    'settings.gradle.kts',
    'settings-gradle.lockfile',
    'gradle.lockfile',
    'gradle.properties',
    'gradlew',
    'gradlew.bat',
    'pyproject.toml',
    'uv.lock',
    '.python-version',
    '.pre-commit-config.yaml',
)


def test_controlled_root_has_only_eleven_directories_and_three_files() -> None:
    result = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    # 未提交迁移中，index 仍列出已删除旧路径；新受控文件也必须参与验收。
    paths = (Path(name) for name in result.stdout.split('\0') if name)
    names = {
        path.parts[0] for path in paths if (ROOT / path).exists() or (ROOT / path).is_symlink()
    }
    assert names == ROOT_DIRECTORIES | ROOT_FILES
    for name in ROOT_DIRECTORIES:
        assert (ROOT / name).is_dir() and not (ROOT / name).is_symlink(), name
    for name in ROOT_FILES:
        assert (ROOT / name).is_file() and not (ROOT / name).is_symlink(), name


def test_old_root_entries_have_no_copies_or_forwarding_links() -> None:
    for name in OLD_ENTRIES:
        assert not (ROOT / name).exists() and not (ROOT / name).is_symlink(), name


def test_owner_directories_contain_the_unique_tool_entrypoints() -> None:
    for name in (
        'scripts/pyproject.toml',
        'scripts/uv.lock',
        'scripts/.python-version',
        'scripts/.pre-commit-config.yaml',
        '.claude/CLAUDE.md',
        'java/build.gradle.kts',
        'java/settings.gradle.kts',
        'java/gradlew',
        'java/gradlew.bat',
        'java/gradle/VERSION',
        'java/gradle/dependency-locks/root.lockfile',
        'java/gradle/config/checkstyle/suppressions.xml',
        'java/tests/quality-gates/config/web-quality-baselines.json',
        'scripts/gates/config/technical-terms.json',
        'docs/examples/session-browser.env.example',
    ):
        assert (ROOT / name).is_file() and not (ROOT / name).is_symlink(), name


def test_development_docs_select_nested_configs_and_verify_actual_jdk() -> None:
    text = (ROOT / 'docs/development/README.md').read_text(encoding='utf-8')
    for command in (
        'uv sync --project scripts --frozen --extra dev',
        'python -m pytest -c scripts/pyproject.toml --rootdir . scripts/tests',
        'pre-commit install --config scripts/.pre-commit-config.yaml',
        './java/gradlew -p java check',
        './java/gradlew -p java --version',
        '"$JAVA_HOME/bin/java" -version',
    ):
        assert command in text, command
    assert 'Launcher JVM 和 Daemon JVM 均为 25' in text
