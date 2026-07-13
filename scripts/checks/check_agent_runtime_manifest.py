#!/usr/bin/env python3
"""检查 agent-runtime.manifest.yaml 完整性和引用有效性。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import yaml
from scripts.agent_runtime.events.adapter import RUNTIME_EVENTS
from scripts.checks._framework import repository_root
from scripts.checks._registry import CHECKS

ROOT = repository_root()
MANIFEST = ROOT / "harness" / "agent-runtime.manifest.yaml"
GATE_NAME = "agentRuntimeManifest"


REQUIRED_TOP_FIELDS = [
    "version",
    "generated_by",
    "policy_files",
    "protected_roots",
    "platforms",
    "shared_skills",
    "domain_agents",
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
            dispatch = plat_cfg.get("hook_dispatch", {})
            if not isinstance(dispatch, dict):
                errors.append(f"platforms.{plat_name}.hook_dispatch 缺失")
                continue
            entry = dispatch.get("entry")
            if not isinstance(entry, str) or not _check_file_exists(entry):
                errors.append(f"platforms.{plat_name}.hook_dispatch.entry 不存在: {entry}")
            if dispatch.get("client") != plat_name:
                errors.append(f"platforms.{plat_name}.hook_dispatch.client 不一致")
            bindings = dispatch.get("bindings", [])
            if not isinstance(bindings, list) or not bindings:
                errors.append(f"platforms.{plat_name}.hook_dispatch.bindings 为空")
                continue
            for binding in bindings:
                event = binding.get("dispatch_event") if isinstance(binding, dict) else None
                if event not in RUNTIME_EVENTS:
                    errors.append(f"platforms.{plat_name} 包含未知 dispatch_event: {event}")

    shared_skills = data.get("shared_skills", {})
    if isinstance(shared_skills, dict):
        registry_path = shared_skills.get("registry", "")
        if isinstance(registry_path, str) and registry_path:
            if not _check_file_exists(registry_path):
                errors.append(f"shared_skills.registry 文件不存在: {registry_path}")

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
        for check_id in required_gates:
            if not isinstance(check_id, str) or check_id not in CHECKS:
                errors.append(f"required_gates 中包含未注册 check ID: {check_id}")

    for w in warnings:
        warn(w)

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS")
    return 0
