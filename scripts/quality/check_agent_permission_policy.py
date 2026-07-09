#!/usr/bin/env python3
"""检查 .claude/settings.json 权限策略与 manifest permission_policy 一致性。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
SETTINGS_JSON = ROOT / ".claude" / "settings.json"
PRE_WRITE_HOOK = ROOT / ".claude" / "hooks" / "pre-write.sh"
GATE_NAME = "agentPermissionPolicy"


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        message: 用户可读错误信息。

    返回：
        进程退出码。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 解析 manifest 使用的 JSON 兼容 YAML 子集。
def _parse_simple_yaml(text: str) -> dict:
    """参数：
        text: 待解析的 manifest 文本。

    返回：
        解析后的字典。
    """
    lines = text.splitlines()
    return _parse_block(lines, 0, 0)[0]


# 返回行的缩进空格数。
def _indent_level(line: str) -> int:
    """参数：
        line: 待检查的文本行。

    返回：
        缩进空格数。
    """
    return len(line) - len(line.lstrip(" "))


# 解析单个 YAML 标量或行内列表值。
def _parse_value(raw: str):
    """参数：
        raw: 原始 YAML 值文本。

    返回：
        解析后的值对象。
    """
    raw = raw.strip()
    if raw in ("", "~", "null"):
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(item) for item in inner.split(",")]
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


# 递归解析 YAML block。
def _parse_block(lines: list[str], start: int, base_indent: int) -> tuple:
    """参数：
        lines: manifest 文本行列表。
        start: 起始行索引。
        base_indent: 当前块缩进。

    返回：
        二元组，包含解析结果和下一行索引。
    """
    if start >= len(lines):
        return {}, start

    result: dict | list = {}
    is_list = False
    i = start

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = _indent_level(line)
        if indent < base_indent:
            break

        if indent > base_indent and not is_list:
            break

        if stripped.startswith("- "):
            is_list = True
            if not isinstance(result, list):
                result = []
            val_part = stripped[2:].strip()
            if ":" in val_part and not val_part.startswith("["):
                key_part, _, val_part2 = val_part.partition(":")
                key_part = key_part.strip()
                val_part2 = val_part2.strip()
                item_dict = {}
                if val_part2:
                    item_dict[key_part] = _parse_value(val_part2)
                else:
                    child, i = _parse_block(lines, i + 1, indent + 2)
                    item_dict[key_part] = child
                    result.append(item_dict)
                    continue
                result.append(item_dict)
                i += 1
                continue
            else:
                result.append(_parse_value(val_part))
                i += 1
                continue

        if ":" in stripped:
            if isinstance(result, list):
                break
            key, _, val = stripped.partition(":")
            key = key.strip().replace("-", "_")
            val = val.strip()
            if val:
                result[key] = _parse_value(val)
                i += 1
            else:
                child, i = _parse_block(lines, i + 1, indent + 2)
                result[key] = child
        else:
            i += 1

    return result, i


# 加载并解析 manifest。
def _load_manifest() -> dict | None:
    """返回：
        解析后的 manifest；解析失败时返回 None。
    """
    if not MANIFEST.is_file():
        return None
    text = MANIFEST.read_text(encoding="utf-8")
    try:
        return _parse_simple_yaml(text)
    except Exception:
        return None


# 执行权限策略一致性检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    errors: list[str] = []

    # settings.json 必须存在且可解析。
    if not SETTINGS_JSON.is_file():
        return fail(f"文件不存在: {SETTINGS_JSON.relative_to(ROOT)}")

    try:
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return fail(f".claude/settings.json 解析失败: {exc}")

    # 如果 defaultMode == bypassPermissions，检查前置条件。
    permissions = settings.get("permissions", {})
    default_mode = permissions.get("defaultMode", "")

    if default_mode == "bypassPermissions":
        # pre-write.sh hook 必须存在。
        if not PRE_WRITE_HOOK.is_file():
            errors.append(
                "defaultMode 为 bypassPermissions 但 "
                ".claude/hooks/pre-write.sh 不存在"
            )

        # 检查清单中的权限策略字段。
        manifest_data = _load_manifest()
        if manifest_data is None:
            errors.append("manifest 不存在或解析失败，无法验证 permission_policy")
        else:
            perm_policy = manifest_data.get("permission_policy", {})
            if not isinstance(perm_policy, dict):
                errors.append("manifest 缺少 permission_policy 字段")
            else:
                bypass_guard = perm_policy.get(
                    "bypass_permissions_allowed_only_with_pre_write_guard"
                )
                if bypass_guard is not True:
                    errors.append(
                        "manifest permission_policy."
                        "bypass_permissions_allowed_only_with_pre_write_guard "
                        "必须为 true"
                    )

            # manifest 中 Claude pre_write 必须非空。
            platforms = (
                manifest_data.get("platforms", {}) if manifest_data else {}
            )
            claude_cfg = (
                platforms.get("claude", {})
                if isinstance(platforms, dict)
                else {}
            )
            claude_hooks = (
                claude_cfg.get("hooks", {})
                if isinstance(claude_cfg, dict)
                else {}
            )
            pre_write = claude_hooks.get("pre_write", [])
            if not pre_write:
                errors.append(
                    "defaultMode 为 bypassPermissions 但 "
                    "manifest platforms.claude.hooks.pre_write 为空"
                )

    # deny 中必须包含关键规则。
    deny_list = permissions.get("deny", [])

    required_deny_patterns = {
        ".env": False,
        "~/.ssh/**": False,
    }

    for pattern_key in required_deny_patterns:
        for deny_entry in deny_list:
            if pattern_key in str(deny_entry):
                required_deny_patterns[pattern_key] = True
                break

    for pattern_key, found in required_deny_patterns.items():
        if not found:
            errors.append(f"deny 规则中缺少: {pattern_key}")

    # 检查危险 git reset --hard 或等价规则。
    has_dangerous_bash_deny = False
    for deny_entry in deny_list:
        entry_str = str(deny_entry)
        if "git reset --hard" in entry_str or "git clean -fdx" in entry_str:
            has_dangerous_bash_deny = True
            break
    if not has_dangerous_bash_deny:
        errors.append("deny 规则中缺少危险 Bash 操作拦截（如 git reset --hard）")

    if errors:
        for err in errors:
            print(f"[{GATE_NAME}] FAIL: {err}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
