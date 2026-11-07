#!/usr/bin/env python3
"""验证仓库的 OpenSpec 与 agent-harness 结构。

不负责策略内容或产品业务；由 OpenSpec 命令行、doctor 和治理 Gate 调用。
"""

import sys
from pathlib import Path

REQUIRED_PATHS = [
    # 原 OpenSpec 结构检查要求。
    '.claude/CLAUDE.md',
    'AGENTS.md',
    '.claude/settings.json',
    '.claude/commands',
    '.claude/agents',
    'openspec/specs',
    'openspec/changes',
    'openspec/schemas',
    'openspec/templates',
    'harness/README.md',
    'harness/manifest.yaml',
    'scripts/openspec',
    'scripts/gates/checks',
    'scripts/session-browser.sh',
    # 原 Harness 结构检查要求。
    'harness/agent-policy.manifest.yaml',
    'harness/skill-registry.yaml',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'scripts/openspec/validate_layout.py',
]


def validate(root: Path) -> list[str]:
    """验证必要路径、OpenSpec 目录类型及非归档 change 骨架。"""
    errors = [f'Missing required path: {p}' for p in REQUIRED_PATHS if not (root / p).exists()]
    for name in ('specs', 'changes'):
        if not (root / 'openspec' / name).is_dir():
            errors.append(f'openspec/{name} is not a directory')
    changes = root / 'openspec' / 'changes'
    for change in changes.iterdir() if changes.is_dir() else []:
        if change.name == 'archive' or not change.is_dir():
            continue
        for fname in ('proposal.md', 'tasks.md'):
            if not (change / fname).exists():
                errors.append(f'{change / fname} missing')
    return errors


if __name__ == '__main__':
    errors = validate(Path.cwd())
    if errors:
        print('\n'.join(errors))
        sys.exit(1)
    print('repo structure ok')
