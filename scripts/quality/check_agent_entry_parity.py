#!/usr/bin/env python3
"""检查 Claude/Codex agent 入口 parity：每个 agent 在两个平台都有对应入口且引用共享 skill。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_NAME = "agentEntryParity"

# 需要检查的 agent 列表。所有前置任务已完成，全部 required=True。
AGENT_PAIRS: list[dict[str, object]] = [
    {
        "name": "mhtml-export-specialist",
        "skill": "skills/authoring/feipi-mhtml-export-dev/SKILL.md",
        "claude": ".claude/agents/mhtml-export-specialist.md",
        "codex": ".codex/agents/mhtml-export-specialist.toml",
        "required": True,
    },
    {
        "name": "java-backend-implementer",
        "skill": "skills/authoring/feipi-java-feature-dev/SKILL.md",
        "claude": ".claude/agents/java-backend-implementer.md",
        "codex": ".codex/agents/java-backend-implementer.toml",
        "required": True,
    },
    {
        "name": "session-ingestion-specialist",
        "skill": "skills/authoring/feipi-session-ingestion-dev/SKILL.md",
        "claude": ".claude/agents/session-ingestion-specialist.md",
        "codex": ".codex/agents/session-ingestion-specialist.toml",
        "required": True,
    },
    {
        "name": "ui-implementation-specialist",
        "skill": "skills/authoring/feipi-session-detail-ui-dev/SKILL.md",
        "claude": ".claude/agents/ui-implementation-specialist.md",
        "codex": ".codex/agents/ui-implementation-specialist.toml",
        "required": True,
    },
    {
        "name": "quality-gate-diagnoser",
        "skill": "skills/authoring/feipi-quality-gate-diagnosis/SKILL.md",
        "claude": ".claude/agents/quality-gate-diagnoser.md",
        "codex": ".codex/agents/quality-gate-diagnoser.toml",
        "required": True,
    },
    {
        "name": "privacy-reviewer",
        "skill": "skills/authoring/feipi-privacy-redaction-dev/SKILL.md",
        "claude": ".claude/agents/privacy-reviewer.md",
        "codex": ".codex/agents/privacy-reviewer.toml",
        "required": True,
    },
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


# 检查文件是否引用了指定 skill 路径。
def _check_skill_reference(file_path: Path, skill_rel_path: str) -> bool:
    """参数：
        file_path: 要检查的 agent 入口文件。
        skill_rel_path: 期望引用的 skill 相对路径。

    返回：
        文件是否引用了指定 skill。
    """
    if not file_path.is_file():
        return False
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return skill_rel_path in content
    except (OSError, UnicodeDecodeError):
        return False


# 执行 agent parity 检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    errors: list[str] = []
    warnings: list[str] = []

    for agent in AGENT_PAIRS:
        name = agent["name"]
        skill_path = agent["skill"]
        claude_path_str = agent["claude"]
        codex_path_str = agent["codex"]
        required = agent["required"]

        claude_path = ROOT / claude_path_str
        codex_path = ROOT / codex_path_str

        # 1. 检查 Claude 入口存在。
        if not claude_path.is_file():
            msg = f"agent {name} 缺少 Claude 入口: {claude_path_str}"
            if required:
                errors.append(msg)
            else:
                warnings.append(msg)

        # 2. 检查 Codex 入口存在。
        if not codex_path.is_file():
            msg = f"agent {name} 缺少 Codex 入口: {codex_path_str}"
            if required:
                errors.append(msg)
            else:
                warnings.append(msg)

        # 3. 检查 Claude 入口引用 skill。
        if claude_path.is_file() and not _check_skill_reference(claude_path, skill_path):
            msg = f"agent {name} Claude 入口未引用 {skill_path}: {claude_path_str}"
            if required:
                errors.append(msg)
            else:
                warnings.append(msg)

        # 4. 检查 Codex 入口引用 skill。
        if codex_path.is_file() and not _check_skill_reference(codex_path, skill_path):
            msg = f"agent {name} Codex 入口未引用 {skill_path}: {codex_path_str}"
            if required:
                errors.append(msg)
            else:
                warnings.append(msg)

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
