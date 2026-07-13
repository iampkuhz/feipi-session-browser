#!/usr/bin/env python3
"""检查 .claude/settings.json 权限策略与 manifest permission_policy 一致性。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import json

import yaml
from scripts.checks._framework import repository_root

ROOT = repository_root()
MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
SETTINGS_JSON = ROOT / ".claude" / "settings.json"
DISPATCHER = ROOT / "scripts" / "harness" / "hook_dispatch.py"


# 加载并解析 manifest。
def _load_manifest() -> dict | None:
    """返回：
    解析后的 manifest；解析失败时返回 None。
    """
    if not MANIFEST.is_file():
        return None
    try:
        data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError):
        return None


# 执行权限策略一致性检查。
def check_permission_policy() -> list[str]:
    """返回 Claude 权限配置与 runtime manifest 的差异。"""
    if not SETTINGS_JSON.is_file():
        return [f"文件不存在: {SETTINGS_JSON.relative_to(ROOT)}"]
    try:
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f".claude/settings.json 解析失败: {exc}"]

    errors: list[str] = []
    permissions = settings.get("permissions", {})
    if permissions.get("defaultMode") == "bypassPermissions":
        if not DISPATCHER.is_file():
            errors.append("defaultMode 为 bypassPermissions 但共享 hook dispatcher 不存在")
        manifest = _load_manifest()
        if manifest is None:
            errors.append("manifest 不存在或解析失败，无法验证 permission_policy")
        else:
            policy = manifest.get("permission_policy", {})
            if not isinstance(policy, dict) or not policy.get(
                "bypass_permissions_allowed_only_with_pre_write_guard"
            ):
                errors.append("manifest permission_policy 未要求 pre-write guard")
            platforms = manifest.get("platforms", {})
            claude = platforms.get("claude", {}) if isinstance(platforms, dict) else {}
            dispatch = claude.get("hook_dispatch", {}) if isinstance(claude, dict) else {}
            bindings = dispatch.get("bindings", []) if isinstance(dispatch, dict) else []
            if not any(item.get("dispatch_event") == "pre-write" for item in bindings):
                errors.append("manifest 缺少 Claude pre-write dispatcher binding")

    deny = [str(item) for item in permissions.get("deny", [])]
    for required in (".env", "~/.ssh/**"):
        if not any(required in item for item in deny):
            errors.append(f"deny 规则中缺少: {required}")
    if not any("git reset --hard" in item or "git clean -fdx" in item for item in deny):
        errors.append("deny 规则中缺少危险 Bash 操作拦截")
    return errors
