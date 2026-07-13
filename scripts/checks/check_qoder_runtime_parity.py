#!/usr/bin/env python3
"""负责验证 Qoder 平台 metadata、共享 dispatcher 与 Skill 入口；不负责执行 Hook；由 Gate 调用。"""

from __future__ import annotations

import json
import sys

import yaml
from scripts.checks._framework import repository_root
from scripts.checks.check_agent_entry_parity import check_agent_entries
from scripts.checks.check_agent_hook_parity import check_hook_parity

ROOT = repository_root()
REQUIRED_FILES = (
    '.qoder/README.md',
    '.qoder/AGENTS.md',
    '.qoder/settings.json',
    '.qoder/settings.local.example.json',
    '.qoder/agents/qoder-main-default.md',
    '.qoder/agents/runtime-isolation-diagnoser.md',
)


def check_qoder_parity() -> list[str]:
    """返回 Qoder 独有入口与共享真源之间的差异。"""
    errors = [
        f'missing required Qoder file: {path}'
        for path in REQUIRED_FILES
        if not (ROOT / path).is_file()
    ]
    try:
        settings = json.loads((ROOT / '.qoder/settings.json').read_text(encoding='utf-8'))
        if settings.get('agent') != 'qoder-main-default':
            errors.append('.qoder/settings.json agent metadata mismatch')
        local = json.loads(
            (ROOT / '.qoder/settings.local.example.json').read_text(encoding='utf-8')
        )
        if local.get('environment') not in ({}, None):
            errors.append('.qoder/settings.local.example.json must not inject runtime identity')
        manifest = yaml.safe_load(
            (ROOT / 'harness/agent-runtime.manifest.yaml').read_text(encoding='utf-8')
        )
        qoder = manifest.get('platforms', {}).get('qoder', {})
        if qoder.get('agents_dir') != '.qoder/agents' or qoder.get('skills_dir') != '.qoder/skills':
            errors.append('manifest Qoder agent/skill metadata mismatch')
        dispatch = qoder.get('hook_dispatch', {})
        if dispatch.get('entry') != 'scripts/harness/hook_dispatch.py':
            errors.append('manifest Qoder dispatcher authority mismatch')
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        errors.append(f'Qoder metadata parse failed: {exc}')
    errors.extend(check_agent_entries('qoder'))
    errors.extend(error for error in check_hook_parity() if error.startswith('qoder'))
    return errors


def main() -> int:
    """运行 Qoder Runtime 等价检查并按统一进程退出码报告结果。"""
    errors = check_qoder_parity()
    for error in errors:
        print(f'[qoderRuntimeParity] FAIL: {error}', file=sys.stderr)
    if errors:
        return 1
    print('[qoderRuntimeParity] PASS skipped_count=0')
    return 0
