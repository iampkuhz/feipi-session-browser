import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import scripts.agent_runtime.change.candidate as candidate_module
from scripts.agent_runtime.change.candidate import (
    CandidateError,
    collect_manifest,
    prepare_candidate,
    stage_exact,
)


def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=repo, text=True, capture_output=True, check=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    run(root, 'git', 'init', '-b', 'main_java')
    run(root, 'git', 'config', 'user.email', 'candidate@example.invalid')
    run(root, 'git', 'config', 'user.name', 'Candidate Test')
    (root / 'keep.txt').write_text('keep\n', encoding='utf-8')
    (root / 'delete.txt').write_text('delete\n', encoding='utf-8')
    run(root, 'git', 'add', '.')
    run(root, 'git', 'commit', '-m', 'initial')
    return root


def record(**updates):
    value = {'allowedPaths': ['.'], 'forbiddenPaths': ['.env', 'data']}
    value.update(updates)
    return value


def test_exact_manifest_supports_staged_deletion_and_does_not_add_again(repo, monkeypatch):
    run(repo, 'git', 'rm', 'delete.txt')
    manifest = collect_manifest(repo)
    calls = []
    original_git = candidate_module.git

    def observed_git(selected_repo, *args, **kwargs):
        if args and args[0] == 'add':
            calls.append(args)
        return original_git(selected_repo, *args, **kwargs)

    monkeypatch.setattr(candidate_module, 'git', observed_git)

    # stage_exact uses the shared git wrapper; an already-staged candidate must remain untouched.
    stage_exact(repo, manifest)
    assert manifest.staged == ('delete.txt',)
    assert calls == []
    assert run(repo, 'git', 'diff', '--cached', '--name-status').stdout == 'D\tdelete.txt\n'


def test_exact_manifest_supports_unstaged_deletion_untracked_and_mixed_path(repo):
    (repo / 'delete.txt').unlink()
    (repo / 'new.txt').write_text('new\n', encoding='utf-8')
    (repo / 'keep.txt').write_text('staged\n', encoding='utf-8')
    run(repo, 'git', 'add', 'keep.txt')
    (repo / 'keep.txt').write_text('working\n', encoding='utf-8')
    manifest = collect_manifest(repo)
    assert set(manifest.paths) == {'delete.txt', 'keep.txt', 'new.txt'}
    assert manifest.staged == ('keep.txt',)

    stable = stage_exact(repo, manifest)

    assert stable.staged == stable.paths
    assert stable.unstaged == stable.untracked == ()
    assert (repo / 'keep.txt').read_text(encoding='utf-8') == 'working\n'


def test_scope_escape_is_blocked_before_index_mutation(repo):
    (repo / 'keep.txt').write_text('changed\n', encoding='utf-8')
    (repo / 'outside.txt').write_text('outside\n', encoding='utf-8')
    before = run(repo, 'git', 'diff', '--cached', '--binary').stdout

    with pytest.raises(CandidateError, match='outside allowed scope'):
        prepare_candidate(repo, record(allowedPaths=['keep.txt']))

    assert run(repo, 'git', 'diff', '--cached', '--binary').stdout == before


def test_formatter_owned_change_is_restaged_and_stabilizes(repo):
    (repo / 'keep.txt').write_text('before\n', encoding='utf-8')
    calls = 0

    def formatter(_argv):
        nonlocal calls
        calls += 1
        if calls == 1:
            (repo / 'keep.txt').write_text('formatted\n', encoding='utf-8')
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    prepared = prepare_candidate(
        repo,
        record(),
        formatter_argv=['formatter'],
        run_formatter=formatter,
    )

    assert calls == 2
    assert prepared.formatter_runs == 2
    assert run(repo, 'git', 'show', ':keep.txt').stdout == 'formatted\n'


def test_formatter_receives_each_manifest_path_once(repo):
    (repo / 'keep.txt').write_text('before\n', encoding='utf-8')
    commands = []

    def formatter(argv):
        commands.append(list(argv))
        return SimpleNamespace(returncode=0)

    prepared = prepare_candidate(
        repo,
        record(),
        formatter_argv=['formatter', '--stable'],
        run_formatter=formatter,
    )

    assert prepared.formatter_runs == 1
    assert commands == [['formatter', '--stable', 'keep.txt']]


def test_default_stabilizer_runs_only_source_modifying_ruff_hooks(repo, monkeypatch):
    from scripts.agent_runtime.change import runtime

    (repo / 'keep.txt').write_text('before\n', encoding='utf-8')
    commands = []
    log_paths = []
    monkeypatch.setattr(candidate_module, 'default_formatter_argv', lambda _repo: ('precommit',))

    def bounded(command, **kwargs):
        commands.append(list(command))
        log_paths.append(kwargs['log_path'])
        return SimpleNamespace(return_code=0, passed=True)

    monkeypatch.setattr(runtime, 'run_bounded', bounded)
    injected_log_dir = repo.parent / 'runtime' / 'candidate'
    prepared = prepare_candidate(repo, record(), log_dir=injected_log_dir)

    assert prepared.formatter_runs == 1
    assert commands == [
        ['precommit', 'run', 'ruff-format', '--files', 'keep.txt'],
        ['precommit', 'run', 'ruff', '--files', 'keep.txt'],
    ]
    assert log_paths == [
        injected_log_dir / 'formatter-ruff-format.log',
        injected_log_dir / 'formatter-ruff.log',
    ]


def test_formatter_second_pass_mutation_is_repair_required_without_losing_index(repo):
    (repo / 'keep.txt').write_text('before\n', encoding='utf-8')
    calls = 0

    def formatter(_argv):
        nonlocal calls
        calls += 1
        (repo / 'keep.txt').write_text(f'pass-{calls}\n', encoding='utf-8')
        return SimpleNamespace(returncode=1)

    with pytest.raises(CandidateError) as captured:
        prepare_candidate(
            repo,
            record(),
            formatter_argv=['formatter'],
            run_formatter=formatter,
        )

    assert captured.value.code == 'FORMATTER_UNSTABLE'
    assert run(repo, 'git', 'show', ':keep.txt').stdout == 'pass-1\n'
    assert (repo / 'keep.txt').read_text(encoding='utf-8') == 'pass-2\n'


def test_formatter_scope_escape_keeps_new_path_unstaged(repo):
    (repo / 'keep.txt').write_text('before\n', encoding='utf-8')

    def formatter(_argv):
        (repo / 'outside.txt').write_text('unexpected\n', encoding='utf-8')
        return SimpleNamespace(returncode=1)

    with pytest.raises(CandidateError) as caught:
        prepare_candidate(
            repo,
            record(),
            formatter_argv=['formatter'],
            run_formatter=formatter,
        )

    assert caught.value.code == 'FORMATTER_SCOPE_ESCAPE'
    assert (
        subprocess.run(
            ['git', 'ls-files', '--error-unmatch', 'outside.txt'], cwd=repo, check=False
        ).returncode
        != 0
    )
