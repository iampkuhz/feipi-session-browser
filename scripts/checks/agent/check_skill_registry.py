"""检查 skill-registry.yaml 的源目录、入口链接、必需文件和命名。

registry 完整性可保证各客户端入口仍指向同一 Skill 真源。公开入口是 `check(arguments)`；
返回诊断表示 registry 无法解析、结构不完整或入口与真源不一致。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import yaml
from scripts.checks._framework import CheckResult, argument_parser, repository_root

if TYPE_CHECKING:
    from pathlib import Path

ROOT = repository_root()
REGISTRY = ROOT / "harness" / "skill-registry.yaml"
KEBAB_CASE_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")

# SKILL.md 副本超过此字节数且非 symlink 时视为非法复制。
_MAX_ENTRY_SKILL_MD_BYTES = 2000


def _load_registry() -> dict | None:
    """加载 skill registry；文件无效或解析失败时返回 None。"""
    if not REGISTRY.is_file():
        return None
    try:
        data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError):
        return None


def _check_entry_not_copy(entry_path: Path, source_path: Path) -> str | None:
    """拒绝入口目录复制过长 SKILL.md，合法链接或短入口不报错。"""
    entry_skill_md = entry_path / "SKILL.md"
    if not entry_skill_md.exists():
        return None

    # 链接和同 inode 都保留单一真源，不按正文副本处理。
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


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回 Skill registry 完整性检查结果。"""
    parser = argument_parser(description='检查 Skill registry 完整性')
    parser.parse_args(arguments)
    # 先建立可信 registry 模型；无法解析时不继续猜测配置。
    if not REGISTRY.is_file():
        return CheckResult.from_errors([f"registry 不存在: {REGISTRY.relative_to(ROOT)}"])

    data = _load_registry()
    if data is None:
        return CheckResult.from_errors(["registry 解析失败"])

    errors: list[str] = []

    # 顶层契约不完整时立即汇总失败，避免后续派生误报。
    required_fields = ["version", "source_root", "entry_roots", "skills", "rules"]
    for field in required_fields:
        if field not in data:
            errors.append(f"缺少顶层字段: {field}")

    if errors:
        return CheckResult.from_errors(errors)

    # 验证共享真源根目录。
    source_root = data.get("source_root", "")
    if isinstance(source_root, str) and source_root:
        if not (ROOT / source_root).is_dir():
            errors.append(f"source_root 不存在: {source_root}")
    else:
        errors.append("source_root 为空或缺失")

    # 逐项验证命名、真源文件和各平台薄入口。
    skills = data.get("skills", {})
    if not isinstance(skills, dict):
        errors.append("skills 字段不是 dict")
        skills = {}

    for skill_name, skill_cfg in skills.items():
        if not isinstance(skill_cfg, dict):
            errors.append(f"skill {skill_name} 配置不是 dict")
            continue

        # registry 名称直接映射目录与入口，因此统一使用 kebab-case。
        if not KEBAB_CASE_RE.match(skill_name):
            errors.append(f"skill 名称不是 kebab-case: {skill_name}")

        source = skill_cfg.get("source", "")
        if isinstance(source, str) and source:
            source_path = ROOT / source
            if not source_path.is_dir():
                errors.append(f"skill {skill_name} source 不存在: {source}")
            else:
                required_files = skill_cfg.get("required_files", [])
                if isinstance(required_files, list):
                    for rf in required_files:
                        if isinstance(rf, str) and not (source_path / rf).is_file():
                            errors.append(f"skill {skill_name} 缺少必需文件: {rf}")

        exposed_in = skill_cfg.get("exposed_in", [])
        if isinstance(exposed_in, list):
            for entry in exposed_in:
                if not isinstance(entry, str):
                    continue
                entry_path = ROOT / entry
                if not entry_path.exists():
                    errors.append(f"skill {skill_name} exposed entry 不存在: {entry}")
                elif entry_path.is_symlink():
                    target = entry_path.resolve()
                    if not target.exists():
                        errors.append(
                            f"skill {skill_name} entry symlink 目标不存在:"
                            f" {entry} -> {os.readlink(entry_path)}"
                        )
                else:
                    # 普通目录只能保留短入口，避免平台副本漂移。
                    if isinstance(source, str) and source:
                        copy_err = _check_entry_not_copy(entry_path, ROOT / source)
                        if copy_err:
                            errors.append(copy_err)

    return CheckResult.from_errors(errors)
