#!/usr/bin/env python3
"""检查 Claude 项目 settings 的静态敏感路径与破坏性命令 deny 规则。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.checks._framework import repository_root

ROOT = repository_root()
SETTINGS_JSON = ROOT / '.claude' / 'settings.json'


def check_permission_policy(_args: list[str] | None = None) -> list[str]:
    """返回缺失或无效的静态 permission deny 规则；不依赖平台 Hook。"""
    settings_path = SETTINGS_JSON
    if not settings_path.is_file():
        return [f'文件不存在: {settings_path.relative_to(ROOT)}']
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as exc:
        return [f'.claude/settings.json 解析失败: {exc}']

    permissions = settings.get('permissions', {})
    deny = [str(item) for item in permissions.get('deny', [])]
    errors: list[str] = []
    for required in ('.env', '.mcp.json', '~/.ssh/**', '~/.aws/**', '~/.config/gh/hosts.yml'):
        if not any(required in item for item in deny):
            errors.append(f'deny 规则中缺少: {required}')
    dangerous = ('git reset --hard', 'git clean -fdx', 'rm -rf /', 'dd if=')
    for command in dangerous:
        if not any(command in item for item in deny):
            errors.append(f'deny 规则中缺少危险 Bash 操作: {command}')
    return errors
