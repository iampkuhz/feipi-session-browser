#!/usr/bin/env python3
"""检查 Agent 规约体积是否符合共享 manifest 和 Codex 配置限制。

体积边界可防止入口文档被客户端截断。公开入口是 `check(arguments)`；返回诊断表示必需配置
缺失、AGENTS.md 超限或 Codex 读取上限不足。
"""

from __future__ import annotations

import re

from scripts.checks._framework import CheckResult, argument_parser, repository_root

ROOT = repository_root()
POLICY_MANIFEST = ROOT / "harness" / "agent-policy.manifest.yaml"
CODEX_CONFIG = ROOT / ".codex" / "config.toml"


def _parse_size_limits(text: str) -> dict[str, int]:
    """从 policy manifest 文本中解析文件名到字节上限的映射。"""
    result: dict[str, int] = {}
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "size_limits:":
            in_section = True
            continue
        if in_section:
            if not stripped or (not line.startswith(" ") and ":" in stripped):
                break
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                try:
                    result[key] = int(val)
                except ValueError:
                    pass
    return result


def _read_codex_max() -> int | None:
    """读取 Codex 项目文档上限；配置不存在或未声明时返回 None。"""
    if not CODEX_CONFIG.is_file():
        return None
    for line in CODEX_CONFIG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"project_doc_max_bytes\s*=\s*(\d+)", line.strip())
        if m:
            return int(m.group(1))
    return None


def check(arguments: list[str]) -> CheckResult:
    """解析参数并返回共享规约与 Codex 配置的体积检查结果。"""
    parser = argument_parser(description='检查 Agent 规约体积限制')
    parser.parse_args(arguments)
    if not POLICY_MANIFEST.is_file():
        return CheckResult.from_errors(
            [f"policy manifest 不存在: {POLICY_MANIFEST.relative_to(ROOT)}"]
        )

    manifest_text = POLICY_MANIFEST.read_text(encoding="utf-8")
    size_limits = _parse_size_limits(manifest_text)
    if not size_limits:
        return CheckResult.from_errors(["policy manifest 缺少 size_limits"])

    agents_limit = size_limits.get("AGENTS.md")
    if agents_limit is None:
        return CheckResult.from_errors(["policy manifest size_limits 缺少 AGENTS.md 限制"])

    agents_file = ROOT / "AGENTS.md"

    errors: list[str] = []

    # AGENTS.md 是硬限制，缺失或超限都阻断 Gate。
    if agents_file.is_file():
        agents_size = agents_file.stat().st_size
        if agents_size > agents_limit:
            errors.append(f"AGENTS.md {agents_size} bytes 超过限制 {agents_limit} bytes")
    else:
        return CheckResult.from_errors(["AGENTS.md 不存在"])

    # Codex 读取上限还需预留少量增长空间，避免入口文档被截断。
    codex_max = _read_codex_max()
    if codex_max is not None and agents_file.is_file():
        agents_size = agents_file.stat().st_size
        needed = agents_size + 100
        if codex_max < needed:
            errors.append(
                f".codex/config.toml project_doc_max_bytes={codex_max} "
                f"< AGENTS.md size({agents_size}) + 100 = {needed}"
            )

    return CheckResult.from_errors(errors)
