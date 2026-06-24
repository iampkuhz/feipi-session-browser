import pytest
from scripts.claude_hooks.evidence import read_changed_files, record_changed_file
from scripts.claude_hooks.hook_io import read_stdin_json
from scripts.claude_hooks.paths import RepoPaths


@pytest.mark.contract_case('HOOK-HARNESS-003')
def test_record_changed_file(tmp_path):
    repo = tmp_path
    target = repo / 'java/core/src/main/java/Foo.java'
    target.parent.mkdir(parents=True)
    target.write_text('class Foo {}\n')
    paths = RepoPaths(repo_root=repo, agent_log_dir=repo / 'tmp/agent_logs/session1')
    ctx = read_stdin_json(
        'post-write', '{"tool_name":"Edit","tool_input":{"file_path":"java/core/src/main/java/Foo.java"}}'
    )
    record = record_changed_file(paths, ctx, 'java/core/src/main/java/Foo.java')
    assert record['category'] == 'java-src'
    rows = read_changed_files(paths)
    assert len(rows) == 1
