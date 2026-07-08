#!/usr/bin/env python3
"""检查 Claude/Codex/Qoder hook parity：pre_bash、pre_write、post_bash、post_write、stop。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
CODEX_HOOKS_JSON = ROOT / ".codex" / "hooks.json"
GATE_NAME = "agentHookParity"

REQUIRED_HOOK_KEYS = ["pre_bash", "pre_write", "post_bash", "post_write", "stop"]
PLATFORMS = ["claude", "codex", "qoder"]


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
            pre_tool_use = hooks_data.get("hooks", {}).get("PreToolUse", [])
            write_matcher_found = False
            for entry in pre_tool_use:
                matcher = entry.get("matcher", "")
                if "Write" in matcher and "Edit" in matcher:
                    write_matcher_found = True
                    break
            if not write_matcher_found:
                errors.append(
                    ".codex/hooks.json PreToolUse 缺少 "
                    "Write|Edit|MultiEdit|NotebookEdit matcher"
                )

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
