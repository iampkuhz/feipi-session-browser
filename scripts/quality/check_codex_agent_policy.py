#!/usr/bin/env python3
"""Validate Codex custom agent metadata and handoff contracts."""

from __future__ import annotations

import argparse
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / '.codex' / 'agents'

READ_ONLY_AGENTS = {
    'migration-planner',
    'qa-verifier',
    'repo-mapper',
    'ui-architect',
}

WRITE_CAPABLE_AGENTS = {
    'implementer',
    'mhtml-export-specialist',
    'openspec-planner',
}

ALLOWED_REASONING_EFFORTS = {'low', 'medium', 'high', 'xhigh'}
MIN_DEVELOPER_INSTRUCTIONS_CHARS = 300


def _load(path: Path) -> dict:
    """Load one agent TOML file for the Codex agent policy gate.

    Args:
        path: Agent config path under ``.codex/agents``.

    Returns:
        Parsed TOML mapping used by downstream contract checks.

    Raises:
        ValueError: Raised when the file cannot be parsed as TOML.
    """
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        raise ValueError(f'{path.relative_to(REPO_ROOT)}: TOML 解析失败: {exc}') from exc


def check_agent(path: Path) -> list[str]:
    """Validate one Codex agent config and return contract failures.

    Args:
        path: Agent TOML path selected by the quality gate.

    Returns:
        Failure messages. The list is empty when metadata, sandbox mode, and
        handoff wording satisfy the repository's custom agent policy.
    """
    failures: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    data = _load(path)

    name = data.get('name')
    description = data.get('description')
    instructions = data.get('developer_instructions')

    if name != path.stem:
        failures.append(f'{rel}: name 必须等于文件名 `{path.stem}`')
    if not isinstance(description, str) or not description.strip():
        failures.append(f'{rel}: description 不能为空')
    if (
        not isinstance(instructions, str)
        or len(instructions.strip()) < MIN_DEVELOPER_INSTRUCTIONS_CHARS
    ):
        failures.append(f'{rel}: developer_instructions 过短, 无法承载 handoff 和边界契约')

    if 'model' in data:
        failures.append(f'{rel}: 不要固定 model; 省略 model 以继承 parent session')

    effort = data.get('model_reasoning_effort')
    if effort is not None and effort not in ALLOWED_REASONING_EFFORTS:
        failures.append(f'{rel}: model_reasoning_effort 非法: {effort}')

    sandbox = data.get('sandbox_mode')
    if name in READ_ONLY_AGENTS and sandbox != 'read-only':
        failures.append(f'{rel}: 只读 agent 必须设置 sandbox_mode = "read-only"')
    if name in WRITE_CAPABLE_AGENTS and sandbox == 'read-only':
        failures.append(f'{rel}: 可写 agent 不得设置 sandbox_mode = "read-only"')

    text = instructions or ''
    for token in ('Handoff', 'BLOCKED', '输出固定为'):
        if token not in text:
            failures.append(f'{rel}: developer_instructions 缺少 `{token}` 契约')
    if (
        name not in {'repo-mapper', 'migration-planner', 'ui-architect'}
        and 'Validation' not in text
    ):
        failures.append(f'{rel}: developer_instructions 缺少 `Validation` 契约')

    return failures


def run_check() -> list[str]:
    """Run the Codex agent policy gate across configured custom agents.

    Returns:
        Failure messages for every ``.codex/agents/*.toml`` file. Missing agent
        directory is treated as a passing no-op so other quality targets can run
        in worktrees without local custom agents.
    """
    if not AGENTS_DIR.exists():
        return []
    failures: list[str] = []
    for path in sorted(AGENTS_DIR.glob('*.toml')):
        try:
            failures.extend(check_agent(path))
        except ValueError as exc:
            failures.append(str(exc))
    return failures


def _self_test() -> None:
    """Check fixed policy sets used by the CLI ``--self-test`` path."""
    assert 'implementer' in WRITE_CAPABLE_AGENTS
    assert 'qa-verifier' in READ_ONLY_AGENTS
    assert 'high' in ALLOWED_REASONING_EFFORTS


def main() -> int:
    """Parse CLI flags, run the agent policy gate, and return exit status.

    Returns:
        ``0`` when the self-test or policy scan passes, otherwise ``1`` after
        printing all failures for the quality summary artifact.
    """
    parser = argparse.ArgumentParser(description='检查 Codex custom agent 配置')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print('codex agent policy self-test PASS')
        return 0

    failures = run_check()
    if failures:
        print('codex agent policy FAIL')
        for item in failures:
            print(f'[FAIL] {item}')
        return 1
    print('codex agent policy PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
