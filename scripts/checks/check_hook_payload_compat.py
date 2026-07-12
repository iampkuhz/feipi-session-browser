#!/usr/bin/env python3
"""本模块负责检查三平台 Hook payload 的确定性兼容契约。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_runtime.context import read_stdin_json  # noqa: E402
from scripts.agent_runtime.events.policy.bash import (  # noqa: E402
    evaluate_command,
    is_read_only_command,
)
from scripts.agent_runtime.events.policy.file import pre_write_payload_block_reason  # noqa: E402
from scripts.agent_runtime.policy import is_protected_path  # noqa: E402
from scripts.checks._trigger import (  # noqa: E402
    parse_changed_files,
    skip_if_not_triggered,
)

TRIGGER_PATTERNS = [
    'AGENTS.md',
    'CLAUDE.md',
    '.agents/**',
    '.claude/**',
    '.codex/**',
    '.qoder/**',
    'skills/**',
    'harness/**',
    'scripts/agent_runtime/**/*.py',
    'scripts/hooks/**/*.py',
    'scripts/harness/**/*.py',
    'scripts/harness/**/*.sh',
    'scripts/checks/**/*.py',
]


def _json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_checks() -> list[str]:
    """执行 `run_checks` 对应的仓库检查流程；失败时保留可诊断的退出语义。"""
    passed: list[str] = []

    claude = read_stdin_json(
        'pre-write',
        _json(
            {
                'session_id': 'claude-session',
                'agent_id': 'agent-a',
                'agent_client': 'claude',
                'tool_name': 'Write',
                'tool_input': {'file_path': 'README.md'},
            }
        ),
    )
    _assert(claude.session_id == 'claude-session', 'claude session_id not parsed')
    _assert(claude.agent_id == 'agent-a', 'claude agent_id not parsed')
    _assert(claude.agent_client == 'claude', 'claude agent_client not parsed')
    _assert(claude.candidate_paths == ['README.md'], 'claude file_path not parsed')
    passed.append('claude snake_case payload')

    codex = read_stdin_json(
        'pre-write',
        _json(
            {
                'sessionId': 'codex-session',
                'agentId': 'agent-b',
                'agentClient': 'codex',
                'toolName': 'Edit',
                'toolInput': {'path': 'README.md'},
            }
        ),
    )
    _assert(codex.session_id == 'codex-session', 'codex sessionId not parsed')
    _assert(codex.agent_id == 'agent-b', 'codex agentId not parsed')
    _assert(codex.agent_client == 'codex', 'codex agentClient not parsed')
    _assert(codex.candidate_paths == ['README.md'], 'codex path not parsed')
    passed.append('codex camelCase payload')

    qoder = read_stdin_json(
        'pre-write',
        _json({'client': 'qoder', 'toolName': 'Write', 'toolInput': {'path': 'README.md'}}),
    )
    _assert(qoder.agent_client == 'qoder', 'qoder client not parsed')
    _assert(qoder.candidate_paths == ['README.md'], 'qoder minimal path not parsed')
    _assert(
        not pre_write_payload_block_reason(qoder, REPO_ROOT),
        'qoder unprotected minimal payload should be supported',
    )
    passed.append('qoder minimal payload')

    missing_path = read_stdin_json('pre-write', _json({'tool_name': 'Edit', 'tool_input': {}}))
    _assert(
        pre_write_payload_block_reason(missing_path, REPO_ROOT),
        'missing file path for Edit did not block',
    )
    passed.append('missing file path for Edit')

    protected_write = read_stdin_json(
        'pre-write',
        _json(
            {
                'tool_name': 'Write',
                'tool_input': {'file_path': 'scripts/agent_runtime/hook_entry.py'},
            }
        ),
    )
    _assert(
        is_protected_path('scripts/agent_runtime/hook_entry.py', REPO_ROOT),
        'protected fixture path is not protected',
    )
    _assert(
        pre_write_payload_block_reason(protected_write, REPO_ROOT),
        'missing session id for protected Write did not block',
    )
    passed.append('missing session id for protected Write')

    invalid = read_stdin_json('pre-write', '{not-json')
    _assert(invalid.parse_error is not None, 'invalid JSON did not produce parse_error')
    _assert(
        pre_write_payload_block_reason(invalid, REPO_ROOT),
        'invalid JSON for pre-write did not block',
    )
    passed.append('invalid JSON for pre-write')

    multi = read_stdin_json(
        'pre-write',
        _json(
            {
                'session_id': 's',
                'tool_name': 'MultiEdit',
                'tool_input': {
                    'edits': [
                        {'file_path': 'a.txt'},
                        {'path': 'b.txt'},
                        {'file_path': 'a.txt'},
                    ]
                },
            }
        ),
    )
    _assert(multi.candidate_paths == ['a.txt', 'b.txt'], 'MultiEdit multiple paths not extracted')
    passed.append('MultiEdit multiple paths')

    notebook = read_stdin_json(
        'pre-write',
        _json(
            {
                'session_id': 's',
                'tool_name': 'NotebookEdit',
                'tool_input': {'notebook_path': 'n.ipynb'},
            }
        ),
    )
    _assert(notebook.candidate_paths == ['n.ipynb'], 'NotebookEdit notebook_path not extracted')
    passed.append('NotebookEdit notebook_path')

    dangerous = read_stdin_json(
        'pre-bash',
        _json(
            {
                'sessionId': 's',
                'toolName': 'Bash',
                'toolInput': {'command': 'git reset ' + '--hard HEAD'},
            }
        ),
    )
    _assert(not evaluate_command(dangerous.command).allowed, 'dangerous Bash did not block')
    passed.append('Bash dangerous command')

    readonly = read_stdin_json(
        'pre-bash', _json({'client': 'qoder', 'command': 'git status --short'})
    )
    _assert(readonly.command == 'git status --short', 'root-level Bash command not parsed')
    _assert(is_read_only_command(readonly.command), 'read-only Bash command misclassified')
    _assert(evaluate_command(readonly.command).allowed, 'read-only Bash command was blocked')
    mutating_without_session = read_stdin_json(
        'pre-bash',
        _json({'toolName': 'Bash', 'toolInput': {'command': 'python scripts/build.py'}}),
    )
    _assert(
        not is_read_only_command(mutating_without_session.command)
        and not mutating_without_session.session_id,
        'mutating missing-session fixture invalid',
    )
    passed.append('Bash read-only command')

    return passed


def main() -> int:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
        skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)
    else:
        skip_if_not_triggered(None, TRIGGER_PATTERNS)

    try:
        run_checks()
    except Exception as exc:
        print(f'[hookPayloadCompat] FAIL: {exc}', file=sys.stderr)
        return 1
    print('[hookPayloadCompat] PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
