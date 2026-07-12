#!/usr/bin/env python3
"""本模块负责用合成证据检查 Agent runtime 隔离契约。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_runtime.events.evidence import (  # noqa: E402
    read_recorded_changed_files_from_paths,  # noqa: E402
)
from scripts.agent_runtime.paths import (  # noqa: E402
    agent_log_dir,
    build_paths,
    identity_from_values,
    quality_dir,
)
from scripts.agent_runtime.stop.evidence import (  # noqa: E402
    _read_active_change_id,
    collect_stop_changed_files,
)

GATE_NAME = 'agentRuntimeIsolation'

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


def _write_changed_file(repo_root: Path, client: str, session: str, agent: str, file: str) -> Path:
    identity = identity_from_values(client, session, agent)
    path = agent_log_dir(repo_root, identity) / 'changed-files.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'schemaVersion': 1,
        'sessionId': session,
        'agentId': agent,
        'file': file,
    }
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
    return path


def _write_active_change(path: Path, change_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'change_id': change_id}) + '\n', encoding='utf-8')


def _expect(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _check_client_session_isolation(tmp_root: Path, errors: list[str]) -> None:
    claude_path = _write_changed_file(
        tmp_root, 'claude', 'same-session', '', '.claude/agents/qwen-main-default.md'
    )
    qoder_path = _write_changed_file(tmp_root, 'qoder', 'same-session', '', '.qoder/AGENTS.md')

    claude_files = read_recorded_changed_files_from_paths([claude_path], 'same-session')
    qoder_files = read_recorded_changed_files_from_paths([qoder_path], 'same-session')

    _expect(
        claude_path == tmp_root / 'tmp/agent_logs/claude/same-session/main/changed-files.jsonl',
        'claude changed-files path is not client/session/main scoped',
        errors,
    )
    _expect(
        qoder_path == tmp_root / 'tmp/agent_logs/qoder/same-session/main/changed-files.jsonl',
        'qoder changed-files path is not client/session/main scoped',
        errors,
    )
    _expect(
        claude_files == ['.claude/agents/qwen-main-default.md'],
        'claude changed-files record leaked or was not read',
        errors,
    )
    _expect(
        qoder_files == ['.qoder/AGENTS.md'],
        'qoder changed-files record leaked or was not read',
        errors,
    )
    _expect('.qoder/AGENTS.md' not in claude_files, 'qoder file leaked into claude session', errors)


def _check_stop_collection_isolation(tmp_root: Path, errors: list[str]) -> None:
    """执行 `_check_stop_collection_isolation` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
    _write_changed_file(tmp_root, 'qoder', 'session-a', '', 'scripts/checks/check_a.py')
    _write_changed_file(tmp_root, 'qoder', 'session-b', '', 'scripts/checks/check_b.py')

    identity = identity_from_values('qoder', 'session-a', '')
    session_result = collect_stop_changed_files(identity, 'session-a', repo_root=tmp_root)
    _expect(
        session_result.evidence_mode == 'identity-session',
        'main session mode is not identity-session',
        errors,
    )
    _expect(
        session_result.changed_files == ['scripts/checks/check_a.py'],
        'same-client different-session evidence was not isolated',
        errors,
    )

    _write_changed_file(tmp_root, 'claude', 'session-a', '', '.claude/agents/qwen-main-default.md')
    _write_changed_file(tmp_root, 'claude', 'session-a', 'worker-1', 'scripts/checks/check_x.py')
    _write_changed_file(tmp_root, 'claude', 'session-a', 'worker-2', 'AGENTS.md')
    _write_changed_file(tmp_root, 'claude', 'session-b', 'worker-3', 'CLAUDE.md')

    main_identity = identity_from_values('claude', 'session-a', '')
    main_result = collect_stop_changed_files(main_identity, 'session-a', repo_root=tmp_root)
    _expect(
        main_result.changed_files
        == ['.claude/agents/qwen-main-default.md', 'scripts/checks/check_x.py', 'AGENTS.md'],
        'main stop did not collect main and same-session subagents only',
        errors,
    )
    _expect(
        'CLAUDE.md' not in main_result.changed_files,
        'other session agent leaked to main stop',
        errors,
    )

    agent_identity = identity_from_values('claude', 'session-a', 'worker-1')
    agent_result = collect_stop_changed_files(
        agent_identity,
        'session-a',
        agent_id='worker-1',
        repo_root=tmp_root,
    )
    _expect(
        agent_result.evidence_mode == 'identity-agent',
        'subagent mode is not identity-agent',
        errors,
    )
    _expect(
        agent_result.changed_files == ['scripts/checks/check_x.py'],
        'subagent stop did not isolate to its own evidence',
        errors,
    )


def _check_quality_and_active_change_paths(tmp_root: Path, errors: list[str]) -> None:
    claude_main = quality_dir(tmp_root, identity_from_values('claude', 'same-session', ''))
    qoder_main = quality_dir(tmp_root, identity_from_values('qoder', 'same-session', ''))
    qoder_other_session = quality_dir(tmp_root, identity_from_values('qoder', 'other-session', ''))
    qoder_agent = quality_dir(tmp_root, identity_from_values('qoder', 'same-session', 'worker-1'))

    _expect(
        len({claude_main, qoder_main, qoder_other_session, qoder_agent}) == 4,
        'quality directories are not isolated by client/session/agent',
        errors,
    )
    _expect(
        qoder_agent == tmp_root / 'tmp/quality/qoder/same-session/agents/worker-1',
        'subagent quality directory path is incorrect',
        errors,
    )

    agent_identity = identity_from_values('qoder', 'session-a', 'worker-1')
    paths = build_paths(tmp_root, identity=agent_identity)
    expected_candidates = [
        tmp_root / 'tmp/agent_logs/qoder/session-a/agents/worker-1/active_change.json',
        tmp_root / 'tmp/agent_logs/qoder/session-a/main/active_change.json',
        tmp_root / 'openspec/active_change.json',
    ]
    _expect(
        paths.active_change_candidates == expected_candidates,
        'active change candidates do not prefer agent then session',
        errors,
    )
    _write_active_change(paths.active_change_candidates[1], 'session-change')
    _expect(
        _read_active_change_id(agent_identity, repo_root=tmp_root) == 'session-change',
        'session active change fallback not read',
        errors,
    )
    _write_active_change(paths.active_change_candidates[0], 'agent-change')
    _expect(
        _read_active_change_id(agent_identity, repo_root=tmp_root) == 'agent-change',
        'agent active change did not take precedence',
        errors,
    )

    legacy = tmp_root / 'tmp/active_change.json'
    _write_active_change(legacy, 'legacy-change')
    session_identity = identity_from_values('qoder', 'session-a', '')
    legacy_identity = identity_from_values('qoder', '', '')
    _expect(
        build_paths(tmp_root, identity=session_identity).active_change_candidates
        == [
            tmp_root / 'tmp/agent_logs/qoder/session-a/main/active_change.json',
            tmp_root / 'openspec/active_change.json',
        ],
        'session identity unexpectedly uses legacy active change path',
        errors,
    )
    _expect(
        build_paths(tmp_root, identity=legacy_identity).active_change_candidates
        == [tmp_root / 'openspec/active_change.json', legacy],
        'legacy identity does not use tmp/active_change.json',
        errors,
    )
    _expect(
        _read_active_change_id(legacy_identity, repo_root=tmp_root) == 'legacy-change',
        'legacy active change was not read without session identity',
        errors,
    )


def run_checks() -> list[str]:
    """执行 `run_checks` 对应的仓库检查流程；失败时保留可诊断的退出语义。"""
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix='agent-runtime-isolation-') as tmp:
        tmp_root = Path(tmp).resolve()
        _check_client_session_isolation(tmp_root, errors)
        _check_stop_collection_isolation(tmp_root, errors)
        _check_quality_and_active_change_paths(tmp_root, errors)
    return errors


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

    errors = run_checks()
    if errors:
        for error in errors:
            print(f'[{GATE_NAME}] FAIL: {error}', file=sys.stderr)
        return 1
    print(f'[{GATE_NAME}] PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
