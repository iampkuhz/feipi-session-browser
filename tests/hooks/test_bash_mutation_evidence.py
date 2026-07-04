import json
import subprocess

from scripts.claude_hooks.evidence import (
    acquire_bash_mutation_lock,
    release_bash_mutation_lock,
    record_post_bash,
    record_pre_bash_snapshot,
)
from scripts.claude_hooks.hook_io import read_stdin_json
from scripts.claude_hooks.paths import RepoPaths, build_paths, identity_from_values
from scripts.claude_hooks.policy.session_context import handle_session_start


def _git(repo, *args):
    return subprocess.run(
        ['git', *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def test_bash_mutation_records_session_changed_file(tmp_path):
    """Bash hook 前后快照必须把当前 session 的文件修改写入 changed-files evidence。"""
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init')
    tracked = repo / 'scripts' / 'tool.py'
    tracked.parent.mkdir()
    tracked.write_text('print("before")\n', encoding='utf-8')
    _git(repo, 'add', 'scripts/tool.py')
    _git(
        repo,
        '-c',
        'user.name=Test',
        '-c',
        'user.email=test@example.com',
        'commit',
        '-m',
        'init',
    )

    paths = RepoPaths(
        repo_root=repo,
        agent_log_dir=repo / 'tmp' / 'agent_logs' / 'claude' / 'session-a' / 'main',
    )
    ctx = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'session_id': 'session-a',
                'tool_name': 'Bash',
                'tool_use_id': 'tool-1',
                'tool_input': {'command': 'python scripts/tool.py'},
            }
        ),
    )

    assert record_pre_bash_snapshot(paths, ctx)
    tracked.write_text('print("after")\n', encoding='utf-8')

    records = record_post_bash(paths, ctx)

    assert [record['file'] for record in records] == ['scripts/tool.py']
    changed_lines = (paths.changed_files).read_text(encoding='utf-8').splitlines()
    changed_record = json.loads(changed_lines[0])
    assert changed_record['sessionId'] == 'session-a'
    assert changed_record['toolUseId'] == 'tool-1'
    assert changed_record['file'] == 'scripts/tool.py'


def test_bash_snapshots_are_identity_scoped(tmp_path):
    """相同 tool_use_id 在不同 session 下必须写入不同 snapshot 目录。"""
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init')
    tracked = repo / 'README.md'
    tracked.write_text('before\n', encoding='utf-8')
    _git(repo, 'add', 'README.md')
    _git(
        repo,
        '-c',
        'user.name=Test',
        '-c',
        'user.email=test@example.com',
        'commit',
        '-m',
        'init',
    )

    ctx_a = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'session_id': 'session-a',
                'tool_name': 'Bash',
                'tool_use_id': 'same-tool',
                'tool_input': {'command': 'python scripts/tool.py'},
            }
        ),
    )
    ctx_b = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'session_id': 'session-b',
                'tool_name': 'Bash',
                'tool_use_id': 'same-tool',
                'tool_input': {'command': 'python scripts/tool.py'},
            }
        ),
    )
    paths_a = RepoPaths(
        repo_root=repo,
        agent_log_dir=repo / 'tmp' / 'agent_logs' / 'claude' / 'session-a' / 'main',
    )
    paths_b = RepoPaths(
        repo_root=repo,
        agent_log_dir=repo / 'tmp' / 'agent_logs' / 'claude' / 'session-b' / 'main',
    )

    assert record_pre_bash_snapshot(paths_a, ctx_a)
    assert record_pre_bash_snapshot(paths_b, ctx_b)

    snapshots_a = list((paths_a.agent_log_dir / 'bash-snapshots').glob('*.json'))
    snapshots_b = list((paths_b.agent_log_dir / 'bash-snapshots').glob('*.json'))
    assert len(snapshots_a) == 1
    assert len(snapshots_b) == 1
    assert snapshots_a[0] != snapshots_b[0]


def test_bash_mutation_lock_owner_includes_session_identity(tmp_path):
    """相同 tool_use_id 的不同 session 不得释放彼此的 mutation lock。"""
    repo = tmp_path / 'repo'
    repo.mkdir()
    paths_a = build_paths(repo, identity_from_values(agent_client='claude', session_id='session-a'))
    paths_b = build_paths(repo, identity_from_values(agent_client='claude', session_id='session-b'))
    ctx_a = read_stdin_json(
        'pre-bash',
        json.dumps(
            {
                'session_id': 'session-a',
                'tool_name': 'Bash',
                'tool_use_id': 'same-tool',
                'tool_input': {'command': 'python scripts/tool.py'},
            }
        ),
    )
    ctx_b = read_stdin_json(
        'post-bash',
        json.dumps(
            {
                'session_id': 'session-b',
                'tool_name': 'Bash',
                'tool_use_id': 'same-tool',
                'tool_input': {'command': 'python scripts/tool.py'},
            }
        ),
    )

    assert acquire_bash_mutation_lock(paths_a, ctx_a)
    lock_path = repo / 'tmp' / 'agent_logs' / 'bash-mutation.lock'
    assert lock_path.exists()

    release_bash_mutation_lock(paths_b, ctx_b)
    assert lock_path.exists()

    release_bash_mutation_lock(paths_a, ctx_a)
    assert not lock_path.exists()


def test_session_start_and_subagent_start_use_separate_runtime_dirs(tmp_path):
    """SessionStart 与 SubagentStart 必须分别写入 main 和 agent 目录。"""
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init')
    (repo / 'README.md').write_text('init\n', encoding='utf-8')
    _git(repo, 'add', 'README.md')
    _git(
        repo,
        '-c',
        'user.name=Test',
        '-c',
        'user.email=test@example.com',
        'commit',
        '-m',
        'init',
    )

    main_identity = identity_from_values(agent_client='claude', session_id='session-a')
    agent_identity = identity_from_values(
        agent_client='claude',
        session_id='session-a',
        agent_id='agent-1',
    )
    main_paths = build_paths(repo, main_identity)
    agent_paths = build_paths(repo, agent_identity)
    main_ctx = read_stdin_json('session-start', '{"session_id":"session-a"}')
    agent_ctx = read_stdin_json(
        'subagent-start',
        '{"session_id":"session-a","agent_id":"agent-1"}',
    )

    handle_session_start(main_paths, main_ctx, 'session-start')
    handle_session_start(agent_paths, agent_ctx, 'subagent-start')

    assert main_paths.session_id_file.read_text(encoding='utf-8').strip() == 'session-a'
    assert agent_paths.session_id_file.read_text(encoding='utf-8').strip() == 'session-a'
    assert main_paths.base_commit.exists()
    assert agent_paths.base_commit.exists()
    assert main_paths.base_commit != agent_paths.base_commit
    assert main_paths.base_commit.read_text(encoding='utf-8') == agent_paths.base_commit.read_text(
        encoding='utf-8'
    )
