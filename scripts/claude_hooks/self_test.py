from __future__ import annotations

import tempfile
from pathlib import Path

from .hook_io import read_stdin_json
from .classify import classify_file
from .policy.bash_policy import evaluate_command
from .policy.file_policy import evaluate_write_path


# 01. 聚合自测试
def run_self_test() -> None:
    ctx = read_stdin_json("pre-bash", '{"tool_name":"Bash","tool_input":{"command":"pytest -q"}}')
    assert ctx.command == "pytest -q"
    assert classify_file("src/session_browser/web/static/app.css").quality_target == "session-detail"
    assert not evaluate_command("rm -rf /").allowed
    with tempfile.TemporaryDirectory() as d:
        assert evaluate_write_path("src/session_browser/x.py", Path(d)).allowed


# 02. CLI
if __name__ == "__main__":
    run_self_test()
    print("self-test PASS")
