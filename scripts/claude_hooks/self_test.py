"""运行 smoke tests for Claude hook 运行time package。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .classify import classify_file
from .hook_io import read_stdin_json
from .policy.bash_policy import evaluate_command
from .policy.file_policy import evaluate_write_path


# 运行self test。
def run_self_test() -> None:
    ctx = read_stdin_json('pre-bash', '{"tool_name":"Bash","tool_input":{"command":"pytest -q"}}')
    assert ctx.command == 'pytest -q'
    assert (
        classify_file('docs/acceptance-contracts/features/DATA_PRESENTERS.md').quality_target
        == 'acceptance-contracts'
    )
    assert not evaluate_command('rm -rf /').allowed
    with tempfile.TemporaryDirectory() as d:
        assert evaluate_write_path('java/web/src/main/java/com/feipi/Foo.java', Path(d)).allowed


# 02. CLI
if __name__ == '__main__':
    run_self_test()
    print('self-test PASS')
