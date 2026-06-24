"""Run smoke tests for the Claude hook runtime package.

The ``--self-test`` dispatcher path invokes this module to verify parsing,
classification, Bash policy, and file policy behavior without touching real session data.
Failures raise assertions and produce a non-zero process exit.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .classify import classify_file
from .hook_io import read_stdin_json
from .policy.bash_policy import evaluate_command
from .policy.file_policy import evaluate_write_path


# 01. 聚合自测试
def run_self_test() -> None:
    """Run deterministic smoke tests for hook runtime behavior."""
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
