from types import SimpleNamespace

from scripts.harness.agent_stop_check import parse_git_status_paths, required_targets
from scripts.quality import changed_files


def test_parse_git_status_paths_includes_deleted_contract_file():
    output = ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    assert parse_git_status_paths(output) == [
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md'
    ]


def test_deleted_contract_file_requires_acceptance_contract_gate():
    output = ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    paths = parse_git_status_paths(output)
    assert required_targets(paths) == ['acceptance-contracts']


def test_parse_git_status_paths_includes_renames():
    output = 'R  docs/old.md -> docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
    assert parse_git_status_paths(output) == [
        'docs/old.md',
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
    ]


# 01. Windows 路径规范化测试
def test_windows_path_normalization_java():
    """Windows 反斜杠路径必须正确规范化为 java-src target。"""
    from scripts.claude_hooks.classify import classify_file

    c = classify_file('java\\core-domain\\src\\main\\java\\com\\feipi\\Foo.java')
    assert c.quality_target == 'java-src'
    assert c.file == 'java/core-domain/src/main/java/com/feipi/Foo.java'


def test_windows_path_normalization_build():
    """Windows 路径下的 Gradle 文件必须规范化为 java-build target。"""
    from scripts.claude_hooks.classify import classify_file

    c = classify_file('.\\build.gradle.kts')
    assert c.quality_target == 'java-build'


# 02. 多 target Stop 阻断测试
def test_multiple_targets_java_and_hook():
    """Java + hook 文件同时变更时触发两个 target。"""
    targets = required_targets(
        [
            'java/core-domain/src/main/java/com/feipi/Foo.java',
            '.claude/hooks/stop.sh',
        ]
    )
    assert 'java-src' in targets
    assert 'hook-runtime' in targets


def test_stop_blocks_on_java_change():
    """Java 文件变更必须触发 java-src target（不可被 Stop 绕过）。"""
    targets = required_targets(
        [
            'java/core-domain/src/main/java/com/feipi/Foo.java',
        ]
    )
    assert 'java-src' in targets
    assert len(targets) >= 1


def test_shared_changed_files_collects_git_dirty_without_hook_record(monkeypatch, tmp_path):
    """没有 hook changed-files 记录时，git dirty 文件仍必须进入门禁路由。"""

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=0,
            stdout=(
                ' M scripts/quality/run_required_quality_gates.py\n'
                ' D docs/acceptance-contracts/features/DATA_PRESENTERS.md\n'
                '?? .codex/hooks.json\n'
            ),
        )

    monkeypatch.setattr(changed_files.subprocess, 'run', fake_run)

    paths = changed_files.collect_changed_files(
        None,
        repo_root=tmp_path,
        changed_files_path=tmp_path / 'missing.jsonl',
    )

    assert paths == [
        'scripts/quality/run_required_quality_gates.py',
        'docs/acceptance-contracts/features/DATA_PRESENTERS.md',
        '.codex/hooks.json',
    ]
    targets = required_targets(paths)
    assert 'hook-runtime' in targets
    assert 'acceptance-contracts' in targets
