#!/usr/bin/env python3
"""检查 agent-runtime.manifest.yaml 完整性和引用有效性。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
GATE_NAME = "agentRuntimeManifest"

REQUIRED_TOP_FIELDS = [
    "version",
    "generated_by",
    "policy_files",
    "protected_roots",
    "platforms",
    "shared_skills",
    "required_gates",
]


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        message: 用户可读错误信息。

    返回：
        进程退出码。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 输出非阻断告警。
def warn(message: str) -> None:
    """参数：
        message: 用户可读告警信息。
    """
    print(f"[{GATE_NAME}] WARN: {message}")


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


# 检查相对仓库根的文件是否存在且是普通文件。
def _check_file_exists(rel_path: str) -> bool:
    """参数：
        rel_path: 仓库相对路径。

    返回：
        文件是否存在且为普通文件。
    """
    full = ROOT / rel_path
    return full.is_file()


# 执行 manifest 完整性检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    if not MANIFEST.is_file():
        return fail(f"manifest 不存在: {MANIFEST.relative_to(ROOT)}")

    data = _load_manifest()
    if data is None:
        return fail("manifest 解析失败")

    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_TOP_FIELDS:
        key = field
        if key not in data:
            errors.append(f"缺少顶层字段: {field}")

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    policy_files = data.get("policy_files", [])
    if isinstance(policy_files, list):
        for pf in policy_files:
            if isinstance(pf, str) and not _check_file_exists(pf):
                errors.append(f"policy_files 中文件不存在: {pf}")

    platforms = data.get("platforms", {})
    if isinstance(platforms, dict):
        for plat_name, plat_cfg in platforms.items():
            if not isinstance(plat_cfg, dict):
                continue
            cfg_files = plat_cfg.get("config_files", [])
            if isinstance(cfg_files, list):
                for cf in cfg_files:
                    if isinstance(cf, str) and not _check_file_exists(cf):
                        errors.append(f"platforms.{plat_name}.config_files 中文件不存在: {cf}")
            hooks = plat_cfg.get("hooks", {})
            if isinstance(hooks, dict):
                for hook_name, hook_files_list in hooks.items():
                    if not isinstance(hook_files_list, list):
                        continue
                    if not hook_files_list and hook_name == "pre_write":
                        continue
                    for hf in hook_files_list:
                        if isinstance(hf, str) and not _check_file_exists(hf):
                            errors.append(
                                f"platforms.{plat_name}.hooks.{hook_name} 中文件不存在: {hf}"
                            )
                        elif isinstance(hf, str) and not os.path.isfile(ROOT / hf):
                            errors.append(
                                f"platforms.{plat_name}.hooks.{hook_name} 不是普通文件: {hf}"
                            )

    shared_skills = data.get("shared_skills", {})
    if isinstance(shared_skills, dict):
        registry_path = shared_skills.get("registry", "")
        if isinstance(registry_path, str) and registry_path:
            if not _check_file_exists(registry_path):
                errors.append(
                    f"shared_skills.registry 文件不存在: {registry_path}"
                )

        source_root = shared_skills.get("source_root", "")
        if isinstance(source_root, str) and source_root:
            if not (ROOT / source_root).is_dir():
                errors.append(f"shared_skills.source_root 不存在: {source_root}")

        required_skills = shared_skills.get("required", [])
        if isinstance(required_skills, list):
            for skill_name in required_skills:
                if isinstance(skill_name, str):
                    skill_dir = ROOT / source_root / skill_name
                    if not skill_dir.is_dir():
                        errors.append(f"required skill 目录不存在: {skill_name}")
                    elif not (skill_dir / "SKILL.md").is_file():
                        errors.append(f"required skill 缺少 SKILL.md: {skill_name}")

        exposed_roots = shared_skills.get("exposed_roots", [])
        if isinstance(exposed_roots, list):
            any_exists = False
            for er in exposed_roots:
                if isinstance(er, str) and (ROOT / er).is_dir():
                    any_exists = True
                    break
            if not any_exists:
                errors.append("shared_skills.exposed_roots 至少需要一个存在的目录")

    required_gates = data.get("required_gates", [])
    if isinstance(required_gates, list):
        for gate_path in required_gates:
            if isinstance(gate_path, str) and not _check_file_exists(gate_path):
                errors.append(f"required_gates 中脚本不存在: {gate_path}")

    for w in warnings:
        warn(w)

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
