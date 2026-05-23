from scripts.claude_hooks.evidence import record_changed_file, read_changed_files
from scripts.claude_hooks.hook_io import read_stdin_json
from scripts.claude_hooks.paths import RepoPaths


def test_record_changed_file(tmp_path):
    repo = tmp_path
    target = repo / "src/session_browser/a.py"
    target.parent.mkdir(parents=True)
    target.write_text("print(1)\n")
    paths = RepoPaths(repo_root=repo, agent_log_dir=repo / "tmp/agent_logs/session1", legacy_agent_dir=repo / ".agent")
    ctx = read_stdin_json("post-write", '{"tool_name":"Edit","tool_input":{"file_path":"src/session_browser/a.py"}}')
    record = record_changed_file(paths, ctx, "src/session_browser/a.py")
    assert record["category"] == "python-src"
    rows = read_changed_files(paths)
    assert len(rows) == 1
