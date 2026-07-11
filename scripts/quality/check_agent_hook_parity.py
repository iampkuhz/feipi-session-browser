#!/usr/bin/env python3
"""检查 Claude/Codex/Qoder hook parity：pre_bash、pre_write、post_bash、post_write、stop。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
CODEX_HOOKS_JSON = ROOT / ".codex" / "hooks.json"
QODER_SETTINGS_JSON = ROOT / ".qoder" / "settings.json"
GATE_NAME = "agentHookParity"

REQUIRED_HOOK_KEYS = ["pre_bash", "pre_write", "post_bash", "post_write", "stop"]
CODEX_REQUIRED_BINDINGS = {
    ("SessionStart", ""): ".codex/hooks/session-start.sh",
    ("PreToolUse", "Bash"): ".codex/hooks/pre_tool_guard.sh",
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit"): ".codex/hooks/pre_write_guard.sh",
    ("PostToolUse", "Bash"): ".codex/hooks/post_bash_guard.sh",
    ("PostToolUse", "Write|Edit|MultiEdit|NotebookEdit"): ".codex/hooks/post_tool_guard.sh",
    ("PostToolUseFailure", ""): ".codex/hooks/tool_failure.sh",
    ("Stop", ""): ".codex/hooks/stop_check.sh",
    ("StopFailure", ""): ".codex/hooks/stop_failure.sh",
    ("SessionEnd", ""): ".codex/hooks/session_end.sh",
}
PLATFORMS = ["claude", "codex", "qoder"]
QODER_REQUIRED_BINDINGS = {
    ("SessionStart", ""): ".qoder/hooks/session-start.sh",
    ("PreToolUse", "Bash"): ".qoder/hooks/pre_tool_guard.sh",
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit"): ".qoder/hooks/pre_write_guard.sh",
    ("PostToolUse", "Bash"): ".qoder/hooks/post_bash_guard.sh",
    ("PostToolUse", "Write|Edit|MultiEdit|NotebookEdit"): ".qoder/hooks/post_tool_guard.sh",
    ("PostToolUseFailure", ""): ".qoder/hooks/tool_failure.sh",
    ("Stop", ""): ".qoder/hooks/stop_check.sh",
    ("StopFailure", ""): ".qoder/hooks/stop_failure.sh",
    ("SessionEnd", ""): ".qoder/hooks/session_end.sh",
}


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
    if raw == "" or raw == "~" or raw == "null":
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


# 返回 Qoder settings 中指定事件和 matcher 的命令列表。
def _commands_for(settings: dict, event: str, matcher: str) -> list[str]:
    """参数：
        settings: Qoder settings JSON 对象。
        event: hook 事件名。
        matcher: hook matcher；空字符串表示无 matcher。

    返回：
        匹配到的 command hook 列表。
    """
    entries = settings.get("hooks", {}).get(event, [])
    if not isinstance(entries, list):
        return []
    commands: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if matcher and entry.get("matcher") != matcher:
            continue
        if not matcher and entry.get("matcher"):
            continue
        hooks = entry.get("hooks", [])
        if not isinstance(hooks, list):
            continue
        for hook in hooks:
            if isinstance(hook, dict) and hook.get("type") == "command":
                command = hook.get("command")
                if isinstance(command, str):
                    commands.append(command)
    return commands


# 执行 hook parity 检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    if not MANIFEST.is_file():
        return fail(f"manifest 不存在: {MANIFEST.relative_to(ROOT)}")

    data = _load_manifest()
    if data is None:
        return fail("manifest 解析失败")

    platforms = data.get("platforms", {})
    if not isinstance(platforms, dict):
        return fail("manifest 缺少 platforms 字段")

    errors: list[str] = []

    # 1. 检查三个平台都存在。
    for plat in PLATFORMS:
        if plat not in platforms:
            errors.append(f"platforms.{plat} 不存在")

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    # 2. 检查每个平台都有五类 hook key。
    for plat in PLATFORMS:
        plat_cfg = platforms.get(plat, {})
        if not isinstance(plat_cfg, dict):
            errors.append(f"platforms.{plat} 不是 dict")
            continue
        hooks = plat_cfg.get("hooks", {})
        if not isinstance(hooks, dict):
            errors.append(f"platforms.{plat}.hooks 不是 dict")
            continue
        for key in REQUIRED_HOOK_KEYS:
            if key not in hooks:
                # 检查是否有 unsupported reason。
                reason_key = f"{key}_unsupported_reason"
                if reason_key in plat_cfg or reason_key in hooks:
                    continue
                errors.append(
                    f"platforms.{plat}.hooks 缺少 {key}（或 {reason_key}）"
                )

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    # 3. 检查每个 key 要么是非空 list，要么有 unsupported reason。
    for plat in PLATFORMS:
        plat_cfg = platforms.get(plat, {})
        if not isinstance(plat_cfg, dict):
            continue
        hooks = plat_cfg.get("hooks", {})
        if not isinstance(hooks, dict):
            continue
        for key in REQUIRED_HOOK_KEYS:
            val = hooks.get(key)
            if val is None:
                reason_key = f"{key}_unsupported_reason"
                if reason_key in plat_cfg or reason_key in hooks:
                    continue
                errors.append(
                    f"platforms.{plat}.hooks.{key} 为空或 null，且无 {reason_key}"
                )
                continue
            if isinstance(val, list) and len(val) == 0:
                reason_key = f"{key}_unsupported_reason"
                if reason_key in plat_cfg or reason_key in hooks:
                    continue
                errors.append(
                    f"platforms.{plat}.hooks.{key} 是空 list，且无 {reason_key}"
                )
                continue
            if isinstance(val, list):
                for hf in val:
                    if isinstance(hf, str):
                        full_path = ROOT / hf
                        if not full_path.is_file():
                            errors.append(
                                f"platforms.{plat}.hooks.{key} 中文件不存在: {hf}"
                            )

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    # 4. pre_write 对 Claude 和 Codex 必须非空。
    for plat in ["claude", "codex"]:
        plat_cfg = platforms.get(plat, {})
        if not isinstance(plat_cfg, dict):
            continue
        hooks = plat_cfg.get("hooks", {})
        if not isinstance(hooks, dict):
            continue
        pre_write = hooks.get("pre_write")
        if not isinstance(pre_write, list) or len(pre_write) == 0:
            errors.append(
                f"platforms.{plat}.hooks.pre_write 必须非空"
            )

    # 5. Qoder pre_write：如果非空检查文件存在，如果为空必须有 unsupported reason。
    qoder_cfg = platforms.get("qoder", {})
    if isinstance(qoder_cfg, dict):
        qoder_hooks = qoder_cfg.get("hooks", {})
        if isinstance(qoder_hooks, dict):
            qoder_pre_write = qoder_hooks.get("pre_write")
            if (not isinstance(qoder_pre_write, list) or len(qoder_pre_write) == 0):
                reason = (
                    qoder_cfg.get("pre_write_unsupported_reason")
                    or qoder_hooks.get("pre_write_unsupported_reason")
                )
                if not reason:
                    errors.append(
                        "platforms.qoder.hooks.pre_write 为空，"
                        "需要 platforms.qoder.pre_write_unsupported_reason"
                    )
            else:
                for hf in qoder_pre_write:
                    if isinstance(hf, str) and not (ROOT / hf).is_file():
                        errors.append(
                            f"platforms.qoder.hooks.pre_write 中文件不存在: {hf}"
                        )

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    # 6. Codex hooks.json 必须真的包含 Write|Edit|MultiEdit|NotebookEdit 的 PreToolUse。
    if not CODEX_HOOKS_JSON.is_file():
        errors.append(f"文件不存在: {CODEX_HOOKS_JSON.relative_to(ROOT)}")
    else:
        try:
            hooks_data = json.loads(CODEX_HOOKS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f".codex/hooks.json 解析失败: {e}")
            hooks_data = None

        if hooks_data is not None:
            for (event, matcher), expected in CODEX_REQUIRED_BINDINGS.items():
                commands = _commands_for(hooks_data, event, matcher)
                if not any(expected in command and "git rev-parse --show-toplevel" in command for command in commands):
                    suffix = f" matcher={matcher}" if matcher else ""
                    errors.append(f".codex/hooks.json {event}{suffix} 未绑定 Git-root stable command for {expected}")
            stop_commands = _commands_for(hooks_data, "Stop", "")
            for command in stop_commands:
                if ".codex/hooks/stop_check.sh" in command:
                    stop_hook = hooks_data.get("hooks", {}).get("Stop", [])[0].get("hooks", [])[0]
                    if int(stop_hook.get("timeout") or 0) < 1230:
                        errors.append(".codex/hooks.json Stop timeout must exceed 1200s target timeout plus cleanup buffer")

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    # 7. Qoder settings.json 必须真实绑定事件/matcher 到对应 wrapper，且不依赖相对 cwd。
    if not QODER_SETTINGS_JSON.is_file():
        errors.append(f"文件不存在: {QODER_SETTINGS_JSON.relative_to(ROOT)}")
    else:
        try:
            qoder_settings = json.loads(QODER_SETTINGS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            errors.append(f".qoder/settings.json 解析失败: {e}")
            qoder_settings = None
        if qoder_settings is not None:
            for (event, matcher), expected in QODER_REQUIRED_BINDINGS.items():
                commands = _commands_for(qoder_settings, event, matcher)
                if not any(expected in command and "git rev-parse --show-toplevel" in command for command in commands):
                    suffix = f" matcher={matcher}" if matcher else ""
                    errors.append(f".qoder/settings.json {event}{suffix} 未绑定 Git-root stable command for {expected}")
            stop_commands = _commands_for(qoder_settings, "Stop", "")
            for command in stop_commands:
                if ".qoder/hooks/stop_check.sh" in command:
                    stop_hook = qoder_settings.get("hooks", {}).get("Stop", [])[0].get("hooks", [])[0]
                    if int(stop_hook.get("timeout") or 0) < 1230:
                        errors.append(".qoder/settings.json Stop timeout must exceed 1200s target timeout plus cleanup buffer")

    # 8. Local-only settings 治理必须在 .gitignore 和 manifest 中一致。
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").is_file() else ""
    local_only = data.get("permission_policy", {}) if isinstance(data.get("permission_policy"), dict) else {}
    for local_path in [".claude/settings.local.json", ".qoder/settings.local.json"]:
        if local_path not in gitignore:
            errors.append(f".gitignore 缺少 local-only 配置: {local_path}")
    if local_only.get("local_settings_example") != ".claude/settings.local.example.json":
        errors.append("permission_policy.local_settings_example 不一致")
    if local_only.get("qoder_local_settings_example") != ".qoder/settings.local.example.json":
        errors.append("permission_policy.qoder_local_settings_example 不一致")

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
