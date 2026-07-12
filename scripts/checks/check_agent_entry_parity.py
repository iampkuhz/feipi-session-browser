#!/usr/bin/env python3
"""本模块负责执行 `check_agent_entry_parity` 对应的确定性仓库检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GATE_NAME = "agentEntryParity"

from scripts.checks._trigger import (  # noqa: E402
    parse_changed_files,
    skip_if_not_triggered,
)

TRIGGER_PATTERNS = [
    '.claude/agents/**',
    '.codex/agents/**',
    'skills/**',
    'scripts/checks/check_agent_entry_parity.py',
]


@dataclass(frozen=True)
class AgentEntry:
    """一个跨平台 logical agent 的入口声明。"""

    name: str
    claude_path: str | None
    codex_path: str | None
    qoder_path: str | None
    required_skill: str | None
    claude_unsupported_reason: str | None = None
    codex_unsupported_reason: str | None = None
    qoder_unsupported_reason: str | None = None


REQUIRED_LOGICAL_AGENTS: tuple[AgentEntry, ...] = (
    AgentEntry(
        name="main-default",
        claude_path=".claude/agents/qwen-main-default.md",
        codex_path=None,
        qoder_path=".qoder/agents/qoder-main-default.md",
        required_skill=None,
        codex_unsupported_reason="Codex main behavior is configured by .codex/model-instructions.md and .codex/config.toml, not an Agent(...) entry file.",
    ),
    AgentEntry(
        name="java-backend-implementer",
        claude_path=".claude/agents/java-backend-implementer.md",
        codex_path=".codex/agents/java-backend-implementer.toml",
        qoder_path=".qoder/agents/java-backend-implementer.md",
        required_skill="skills/authoring/feipi-java-feature-dev/SKILL.md",
    ),
    AgentEntry(
        name="session-ingestion-specialist",
        claude_path=".claude/agents/session-ingestion-specialist.md",
        codex_path=".codex/agents/session-ingestion-specialist.toml",
        qoder_path=".qoder/agents/session-ingestion-specialist.md",
        required_skill="skills/authoring/feipi-session-ingestion-dev/SKILL.md",
    ),
    AgentEntry(
        name="ui-implementation-specialist",
        claude_path=".claude/agents/ui-implementation-specialist.md",
        codex_path=".codex/agents/ui-implementation-specialist.toml",
        qoder_path=".qoder/agents/ui-implementation-specialist.md",
        required_skill="skills/authoring/feipi-session-detail-ui-dev/SKILL.md",
    ),
    AgentEntry(
        name="mhtml-export-specialist",
        claude_path=".claude/agents/mhtml-export-specialist.md",
        codex_path=".codex/agents/mhtml-export-specialist.toml",
        qoder_path=".qoder/agents/mhtml-export-specialist.md",
        required_skill="skills/authoring/feipi-mhtml-export-dev/SKILL.md",
    ),
    AgentEntry(
        name="quality-gate-diagnoser",
        claude_path=".claude/agents/quality-gate-diagnoser.md",
        codex_path=".codex/agents/quality-gate-diagnoser.toml",
        qoder_path=".qoder/agents/quality-gate-diagnoser.md",
        required_skill="skills/authoring/feipi-quality-gate-diagnosis/SKILL.md",
    ),
    AgentEntry(
        name="privacy-reviewer",
        claude_path=".claude/agents/privacy-reviewer.md",
        codex_path=".codex/agents/privacy-reviewer.toml",
        qoder_path=".qoder/agents/privacy-reviewer.md",
        required_skill="skills/authoring/feipi-privacy-redaction-dev/SKILL.md",
    ),
    AgentEntry(
        name="runtime-isolation-diagnoser",
        claude_path=None,
        codex_path=None,
        qoder_path=".qoder/agents/runtime-isolation-diagnoser.md",
        required_skill=None,
        claude_unsupported_reason="Claude runtime isolation diagnosis is currently handled by quality-gate-diagnoser with runtime gate handoff until a dedicated Claude entry is added.",
        codex_unsupported_reason="Codex runtime isolation diagnosis is currently handled by quality-gate-diagnoser with runtime gate handoff until a dedicated Codex entry is added.",
    ),
    AgentEntry(
        name="repo-mapper",
        claude_path=".claude/agents/repo-mapper.md",
        codex_path=".codex/agents/repo-mapper.toml",
        qoder_path=None,
        required_skill=None,
        qoder_unsupported_reason="Qoder has no dedicated read-only repo mapper entry yet; use qoder-main-default with a read-only scoped mapping handoff until one is added.",
    ),
    AgentEntry(
        name="openspec-planner",
        claude_path=".claude/agents/openspec-planner.md",
        codex_path=".codex/agents/openspec-planner.toml",
        qoder_path=None,
        required_skill="skills/authoring/feipi-openspec-orchestrate-change/SKILL.md",
        qoder_unsupported_reason="Qoder has no dedicated OpenSpec planning entry yet; use qoder-main-default to invoke the OpenSpec skill workflow directly until one is added.",
    ),
)

REQUIRED_CLAUDE_MAIN_SPECIALISTS = (
    "java-backend-implementer",
    "session-ingestion-specialist",
    "ui-implementation-specialist",
    "mhtml-export-specialist",
    "quality-gate-diagnoser",
    "privacy-reviewer",
)

DOMAIN_SPECIALISTS = {
    entry.name
    for entry in REQUIRED_LOGICAL_AGENTS
    if entry.name not in {"main-default", "repo-mapper", "openspec-planner"}
}
GENERIC_DESCRIPTION_MARKERS = (
    "执行任务",
    "执行 scoped task",
    "执行一个 scoped implementation task",
)


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def _path_or_reason(entry: AgentEntry, platform: str) -> tuple[str | None, str | None]:
    return (
        getattr(entry, f"{platform}_path"),
        getattr(entry, f"{platform}_unsupported_reason"),
    )


def _check_declared_path_or_reason(entry: AgentEntry, errors: list[str]) -> None:
    for platform in ("claude", "codex", "qoder"):
        rel_path, reason = _path_or_reason(entry, platform)
        if bool(rel_path) == bool(reason):
            errors.append(
                f"{entry.name} must declare exactly one {platform}_path or {platform}_unsupported_reason"
            )
        if rel_path and not (ROOT / rel_path).is_file():
            errors.append(f"{entry.name} {platform}_path missing: {rel_path}")
        if reason is not None and len(reason.strip()) < 20:
            errors.append(f"{entry.name} {platform}_unsupported_reason is too short")


def _check_skill_reference(entry: AgentEntry, errors: list[str]) -> None:
    if not entry.required_skill:
        return
    if not (ROOT / entry.required_skill).is_file():
        errors.append(f"{entry.name} required_skill missing: {entry.required_skill}")
        return
    for platform in ("claude", "codex", "qoder"):
        rel_path, _reason = _path_or_reason(entry, platform)
        if not rel_path:
            continue
        text = _read(rel_path)
        if entry.required_skill not in text:
            errors.append(
                f"{entry.name} {platform} entry does not reference required_skill: {entry.required_skill}"
            )


def _check_claude_main_allowlist(errors: list[str]) -> None:
    text = _read(".claude/agents/qwen-main-default.md")
    frontmatter = text.split("---", 2)[1] if text.startswith("---") else text
    tools_match = re.search(r"(?m)^tools:\s*(.+)$", frontmatter)
    if not tools_match:
        errors.append("Claude main frontmatter missing tools allowlist")
        return
    tools_line = tools_match.group(1)
    for specialist in REQUIRED_CLAUDE_MAIN_SPECIALISTS:
        if specialist not in tools_line and specialist not in text:
            errors.append(f"Claude main allowlist does not mention specialist: {specialist}")


def _check_description_specificity(entry: AgentEntry, errors: list[str]) -> None:
    if entry.name not in DOMAIN_SPECIALISTS:
        return
    descriptions: dict[str, str] = {}
    for platform in ("codex", "qoder"):
        rel_path, _reason = _path_or_reason(entry, platform)
        if not rel_path:
            continue
        text = _read(rel_path)
        if platform == "codex":
            match = re.search(r'(?m)^description\s*=\s*"([^"]+)"', text)
            description = match.group(1).strip() if match else ""
        else:
            match = re.search(r"(?ms)^## When To Use\n(.*?)(?=\n## )", text)
            description = match.group(1).strip() if match else ""
        descriptions[platform] = re.sub(r"\s+", " ", description)
        if len(descriptions[platform]) < 40:
            errors.append(
                f"{entry.name} {platform} description/When To Use is too short or missing"
            )
        if any(marker == descriptions[platform] for marker in GENERIC_DESCRIPTION_MARKERS):
            errors.append(f"{entry.name} {platform} description is generic")
    if len(set(descriptions.values())) != len(descriptions):
        errors.append(f"{entry.name} Codex/Qoder descriptions are not distinguishable")


def main() -> int:
    """解析命令行参数并运行本文件契约；任一检查失败时返回非零退出码。"""
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    if '--changed-files' in sys.argv:
        idx = sys.argv.index('--changed-files')
        if idx + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[idx + 1])
        skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)
    else:
        skip_if_not_triggered(None, TRIGGER_PATTERNS)

    errors: list[str] = []
    for entry in REQUIRED_LOGICAL_AGENTS:
        _check_declared_path_or_reason(entry, errors)
        _check_skill_reference(entry, errors)
        _check_description_specificity(entry, errors)
    _check_claude_main_allowlist(errors)

    if errors:
        for error in errors:
            print(f"[{GATE_NAME}] FAIL: {error}")
        return 1

    print(
        f"[{GATE_NAME}] PASS: checked {len(REQUIRED_LOGICAL_AGENTS)} logical agents across Claude/Codex/Qoder"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
