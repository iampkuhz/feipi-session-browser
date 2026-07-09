#!/usr/bin/env python3
"""检查 skill-registry.yaml 完整性：源目录、入口链接、必需文件、命名规范。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "harness" / "skill-registry.yaml"
GATE_NAME = "skillRegistry"

KEBAB_CASE_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")

# SKILL.md 副本超过此字节数且非 symlink 时视为非法复制。
_MAX_ENTRY_SKILL_MD_BYTES = 2000


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


# 解析 registry 使用的 JSON 兼容 YAML 子集。
def _parse_simple_yaml(text: str) -> dict:
    """参数：
        text: 待解析的 registry 文本。

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
        lines: 文本行列表。
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
            key = key.strip()
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


# 加载并解析 registry。
def _load_registry() -> dict | None:
    """返回：
        解析后的 registry；解析失败时返回 None。
    """
    if not REGISTRY.is_file():
        return None
    text = REGISTRY.read_text(encoding="utf-8")
    try:
        return _parse_simple_yaml(text)
    except Exception:
        return None


# 检查 entry 是否非法复制了 SKILL.md 正文。
def _check_entry_not_copy(entry_path: Path, source_path: Path) -> str | None:
    """参数：
        entry_path: 入口路径。
        source_path: 真源目录。

    返回：
        错误信息；无问题时返回 None。
    """
    entry_skill_md = entry_path / "SKILL.md"
    if not entry_skill_md.exists():
        return None

    # symlink 或同 inode 视为合法引用。
    if entry_skill_md.is_symlink():
        return None
    try:
        if entry_skill_md.samefile(source_path / "SKILL.md"):
            return None
    except (OSError, FileNotFoundError):
        pass

    if entry_skill_md.stat().st_size > _MAX_ENTRY_SKILL_MD_BYTES:
        return (
            f"entry {entry_path} 包含超过 {_MAX_ENTRY_SKILL_MD_BYTES} bytes 的"
            f" SKILL.md 副本（{entry_skill_md.stat().st_size} bytes），"
            "应使用 symlink 或短 README"
        )
    return None


# 执行 registry 完整性检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    # 1. registry 存在且可解析。
    if not REGISTRY.is_file():
        return fail(f"registry 不存在: {REGISTRY.relative_to(ROOT)}")

    data = _load_registry()
    if data is None:
        return fail("registry 解析失败")

    errors: list[str] = []

    # 检查必需顶层字段。
    required_fields = ["version", "source_root", "entry_roots", "skills", "rules"]
    for field in required_fields:
        if field not in data:
            errors.append(f"缺少顶层字段: {field}")

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    # 2. source_root 存在。
    source_root = data.get("source_root", "")
    if isinstance(source_root, str) and source_root:
        if not (ROOT / source_root).is_dir():
            errors.append(f"source_root 不存在: {source_root}")
    else:
        errors.append("source_root 为空或缺失")

    # 遍历 skills。
    skills = data.get("skills", {})
    if not isinstance(skills, dict):
        errors.append("skills 字段不是 dict")
        skills = {}

    for skill_name, skill_cfg in skills.items():
        if not isinstance(skill_cfg, dict):
            errors.append(f"skill {skill_name} 配置不是 dict")
            continue

        # 8. skill 名称必须 kebab-case。
        if not KEBAB_CASE_RE.match(skill_name):
            errors.append(f"skill 名称不是 kebab-case: {skill_name}")

        # 3. source 存在。
        source = skill_cfg.get("source", "")
        if isinstance(source, str) and source:
            source_path = ROOT / source
            if not source_path.is_dir():
                errors.append(f"skill {skill_name} source 不存在: {source}")
            else:
                # 4. required_files 存在。
                required_files = skill_cfg.get("required_files", [])
                if isinstance(required_files, list):
                    for rf in required_files:
                        if isinstance(rf, str) and not (source_path / rf).is_file():
                            errors.append(
                                f"skill {skill_name} 缺少必需文件: {rf}"
                            )

        # 5 & 6. exposed entries 存在且 symlink 目标有效。
        exposed_in = skill_cfg.get("exposed_in", [])
        if isinstance(exposed_in, list):
            for entry in exposed_in:
                if not isinstance(entry, str):
                    continue
                entry_path = ROOT / entry
                if not entry_path.exists():
                    errors.append(
                        f"skill {skill_name} exposed entry 不存在: {entry}"
                    )
                elif entry_path.is_symlink():
                    # 6. symlink 目标存在。
                    target = entry_path.resolve()
                    if not target.exists():
                        errors.append(
                            f"skill {skill_name} entry symlink 目标不存在:"
                            f" {entry} -> {os.readlink(entry_path)}"
                        )
                else:
                    # 7. 普通目录检查不要复制长正文。
                    if isinstance(source, str) and source:
                        copy_err = _check_entry_not_copy(
                            entry_path, ROOT / source
                        )
                        if copy_err:
                            errors.append(copy_err)

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
