"""检查 Claude 项目 settings 是否拒绝敏感路径和破坏性命令。

完整的 deny 规则可降低密钥泄露和工作区破坏风险。公开入口是 `check(arguments)`；返回诊断
表示 settings 缺失、无法解析或缺少必需规则。
"""

from __future__ import annotations

import json

from scripts.checks._framework import CheckResult, argument_parser, repository_root

ROOT = repository_root()
SETTINGS_JSON = ROOT / '.claude' / 'settings.json'


def _check_permission_policy(settings: object) -> list[str]:
    """检查静态敏感路径与破坏性命令 deny 规则；配置结构错误属于领域违规。"""
    if not isinstance(settings, dict):
        return ['.claude/settings.json 顶层必须是 object']
    permissions = settings.get('permissions', {})
    if not isinstance(permissions, dict):
        return ['.claude/settings.json permissions 必须是 object']
    raw_deny = permissions.get('deny', [])
    if not isinstance(raw_deny, list):
        return ['.claude/settings.json permissions.deny 必须是 array']
    deny = [str(item) for item in raw_deny]
    errors: list[str] = []
    for required in ('.env', '.mcp.json', '~/.ssh/**', '~/.aws/**', '~/.config/gh/hosts.yml'):
        if not any(required in item for item in deny):
            errors.append(f'deny 规则中缺少: {required}')
    dangerous = ('git reset --hard', 'git clean -fdx', 'rm -rf /', 'dd if=')
    for command in dangerous:
        if not any(command in item for item in deny):
            errors.append(f'deny 规则中缺少危险 Bash 操作: {command}')
    return errors


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回 Claude permission policy 检查结果。"""
    parser = argument_parser(description='检查 Claude permission deny 规则')
    parser.parse_args(arguments)
    if not SETTINGS_JSON.is_file():
        return CheckResult.from_errors([f'文件不存在: {SETTINGS_JSON.relative_to(ROOT)}'])
    try:
        settings = json.loads(SETTINGS_JSON.read_text(encoding='utf-8'))
    except OSError as exc:
        return CheckResult.execution_failure(
            [f'.claude/settings.json 读取失败: {exc}'], reason='input-unavailable'
        )
    except json.JSONDecodeError as exc:
        return CheckResult.from_errors([f'.claude/settings.json JSON 内容无效: {exc}'])
    return CheckResult.from_errors(_check_permission_policy(settings))
