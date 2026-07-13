#!/usr/bin/env python3
"""负责验证三平台配置与 manifest 共同调用唯一 Hook dispatcher；不负责执行 Hook；由 Gate 调用。"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import yaml
from scripts.checks._framework import repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
MANIFEST = ROOT / 'harness' / 'agent-runtime.manifest.yaml'
SETTINGS = {
    'claude': ROOT / '.claude' / 'settings.json',
    'codex': ROOT / '.codex' / 'hooks.json',
    'qoder': ROOT / '.qoder' / 'settings.json',
}
DISPATCHER = 'scripts/harness/hook_dispatch.py'


def _load(path: Path) -> dict:
    if path.suffix == '.json':
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError(f'{path.relative_to(ROOT)} must contain an object')
    return data


def _configured_bindings(settings: dict) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    hooks = settings.get('hooks', {})
    if not isinstance(hooks, dict):
        return result
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            matcher = str(entry.get('matcher') or '')
            commands = entry.get('hooks', [])
            if len(commands) == 1 and isinstance(commands[0], dict):
                result[(str(event), matcher)] = commands[0]
    return result


def check_hook_parity() -> list[str]:
    """返回 manifest/config/shared-dispatcher 之间的全部确定性差异。"""
    try:
        manifest = _load(MANIFEST)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f'manifest parse failed: {exc}']
    errors: list[str] = []
    platforms = manifest.get('platforms', {})
    for client, config_path in SETTINGS.items():
        platform = platforms.get(client, {}) if isinstance(platforms, dict) else {}
        dispatch = platform.get('hook_dispatch', {}) if isinstance(platform, dict) else {}
        if dispatch.get('entry') != DISPATCHER or dispatch.get('client') != client:
            errors.append(f'platforms.{client}.hook_dispatch authority mismatch')
            continue
        try:
            configured = _configured_bindings(_load(config_path))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f'{config_path.relative_to(ROOT)} parse failed: {exc}')
            continue
        expected: set[tuple[str, str]] = set()
        for binding in dispatch.get('bindings', []):
            key = (str(binding.get('event') or ''), str(binding.get('matcher') or ''))
            expected.add(key)
            hook = configured.get(key)
            if hook is None:
                errors.append(f'{client} missing hook binding: {key}')
                continue
            command = str(hook.get('command') or '')
            event = str(binding.get('dispatch_event') or '')
            required = (DISPATCHER, f'--client {client}', f'--event {event}')
            if hook.get('type') != 'command' or not all(item in command for item in required):
                errors.append(f'{client} binding does not call shared dispatcher: {key}')
            if 'git rev-parse --show-toplevel' not in command:
                errors.append(f'{client} binding is not Git-root stable: {key}')
            if '/hooks/' in command or '.claude/hooks' in command:
                errors.append(f'{client} binding still calls a platform wrapper: {key}')
            if int(hook.get('timeout') or 0) != int(binding.get('timeout') or 0):
                errors.append(f'{client} timeout drift: {key}')
            if event == 'stop' and int(hook.get('timeout') or 0) < 1230:
                errors.append(f'{client} Stop timeout is below required cleanup buffer')
        extra = set(configured) - expected
        if extra:
            errors.append(f'{client} contains undeclared hook bindings: {sorted(extra)}')

    wrapper_files = [
        path.relative_to(ROOT).as_posix()
        for directory in ('.claude/hooks', '.codex/hooks', '.qoder/hooks')
        for path in (ROOT / directory).glob('*.sh')
    ]
    if wrapper_files:
        errors.append(f'platform hook wrappers still exist: {wrapper_files}')
    if not (ROOT / DISPATCHER).is_file():
        errors.append(f'shared dispatcher missing: {DISPATCHER}')
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for local_path in ('.claude/settings.local.json', '.qoder/settings.local.json'):
        if local_path not in gitignore:
            errors.append(f'.gitignore missing local-only config: {local_path}')
    return errors


def main() -> int:
    """运行 Hook 配置等价检查并按统一进程退出码报告结果。"""
    errors = check_hook_parity()
    for error in errors:
        print(f'[agentHookParity] FAIL: {error}', file=sys.stderr)
    if errors:
        return 1
    print('[agentHookParity] PASS')
    return 0
