#!/usr/bin/env python3
"""Verify Qoder is a first-class runtime entry with agents, hooks, skills, and manifest parity."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_NAME = "qoderRuntimeParity"

REQUIRED_FILES = [
    ".qoder/README.md",
    ".qoder/AGENTS.md",
    ".qoder/settings.json",
    ".qoder/settings.local.example.json",
    ".qoder/hook-bindings.md",
    ".qoder/agents/qoder-main-default.md",
    ".qoder/agents/runtime-isolation-diagnoser.md",
    ".qoder/agents/quality-gate-diagnoser.md",
    ".qoder/agents/java-backend-implementer.md",
    ".qoder/agents/session-ingestion-specialist.md",
    ".qoder/agents/ui-implementation-specialist.md",
    ".qoder/agents/mhtml-export-specialist.md",
    ".qoder/agents/privacy-reviewer.md",
]

AGENTS_HEADINGS = [
    "# Qoder Agent Rules",
    "## Scope",
    "## Startup Rules",
    "## Delegation Rules",
    "## Runtime Identity Rules",
    "## Protected Path Rules",
    "## Validation Rules",
    "## Forbidden Actions",
    "## Final Report Rules",
]

HOOK_HEADINGS = [
    "# Qoder Hook Bindings",
    "## Required Lifecycle Bindings",
    "## PreToolUse Bash",
    "## PreToolUse Write/Edit/MultiEdit/NotebookEdit",
    "## PostToolUse Bash",
    "## PostToolUse Write/Edit/MultiEdit/NotebookEdit",
    "## Stop",
    "## Unsupported Lifecycles",
    "## Required Payload Fields",
    "## Fail-Closed Rules",
    "## Local Verification",
]

MAIN_HEADINGS = [
    "# qoder-main-default",
    "## Role",
    "## Read Order",
    "## Subagent Selection",
    "## Handoff Payload",
    "## Validation Before Final",
    "## Output Format",
]

SPECIALIST_HEADINGS = [
    "## Role",
    "## When To Use",
    "## Must Read",
    "## Allowed Scope",
    "## Forbidden Scope",
    "## Validation",
    "## Output Format",
]

SPECIALIST_SKILLS = {
    "quality-gate-diagnoser": "skills/authoring/feipi-quality-gate-diagnosis/SKILL.md",
    "java-backend-implementer": "skills/authoring/feipi-java-feature-dev/SKILL.md",
    "session-ingestion-specialist": "skills/authoring/feipi-session-ingestion-dev/SKILL.md",
    "ui-implementation-specialist": "skills/authoring/feipi-session-detail-ui-dev/SKILL.md",
    "mhtml-export-specialist": "skills/authoring/feipi-mhtml-export-dev/SKILL.md",
    "privacy-reviewer": "skills/authoring/feipi-privacy-redaction-dev/SKILL.md",
}

RUNTIME_SPECIALIST_PHRASES = {
    "runtime-isolation-diagnoser": [
        "$HOME/Downloads/feipi_agent_env_full_qoder_tasks/shared/EXPECTED_OUTCOMES.md",
        "scripts/claude_hooks/paths.py",
    ]
}

LIFECYCLE_TABLE_HEADER = "| Lifecycle | Matcher | Command | Required | Unsupported reason |\n|---|---|---|---:|---|"
REQUIRED_HOOK_COMMANDS = [
    ".qoder/hooks/session-start.sh",
    ".qoder/hooks/pre_tool_guard.sh",
    ".qoder/hooks/pre_write_guard.sh",
    ".qoder/hooks/post_bash_guard.sh",
    ".qoder/hooks/post_tool_guard.sh",
    ".qoder/hooks/tool_failure.sh",
    ".qoder/hooks/stop_check.sh",
    ".qoder/hooks/stop_failure.sh",
    ".qoder/hooks/session_end.sh",
]

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

# 维护 _commands_for 函数行为。
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
            if isinstance(hook, dict) and hook.get("type") == "command" and isinstance(hook.get("command"), str):
                commands.append(hook["command"])
    return commands


# 维护 _check_settings_json 函数行为。
def _check_settings_json(errors: list[str]) -> None:
    """参数：
        errors: 收集到的错误列表。

    返回：
        无返回值；错误会追加到 errors。
    """
    try:
        settings = json.loads(_read(".qoder/settings.json"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f".qoder/settings.json parse failed: {exc}")
        return
    for (event, matcher), expected in QODER_REQUIRED_BINDINGS.items():
        commands = _commands_for(settings, event, matcher)
        if not any(expected in command and "git rev-parse --show-toplevel" in command for command in commands):
            suffix = f" matcher={matcher}" if matcher else ""
            errors.append(f".qoder/settings.json missing Git-root stable {event}{suffix} binding to {expected}")
    stop_commands = _commands_for(settings, "Stop", "")
    for command in stop_commands:
        if ".qoder/hooks/stop_check.sh" in command:
            stop_hook = settings.get("hooks", {}).get("Stop", [])[0].get("hooks", [])[0]
            if int(stop_hook.get("timeout") or 0) < 1230:
                errors.append(".qoder/settings.json Stop timeout must exceed required gate timeout buffer")
    text = _read(".qoder/settings.local.example.json")
    if "<local-qoder-command>" not in text or "settings.local.json" not in text:
        errors.append(".qoder/settings.local.example.json must be placeholder-only local guidance")


# 维护 _read 函数行为。
def _read(rel_path: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return (ROOT / rel_path).read_text(encoding="utf-8")


# 维护 _headings 函数行为。
def _headings(text: str) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return [line.rstrip() for line in text.splitlines() if line.startswith("#")]


# 维护 _section_text 函数行为。
def _section_text(text: str, heading: str) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    start = text.find(heading)
    if start < 0:
        return ""
    following = re.search(r"\n## ", text[start + len(heading):])
    if not following:
        return text[start:]
    return text[start:start + len(heading) + following.start()]


# 维护 _bullet_count 函数行为。
def _bullet_count(section: str) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return sum(1 for line in section.splitlines() if line.lstrip().startswith("- "))


# 维护 _parse_manifest_text 函数行为。
def _parse_manifest_text() -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return _read("harness/agent-runtime.manifest.yaml")


# 维护 _check_required_files 函数行为。
def _check_required_files(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    for rel_path in REQUIRED_FILES:
        if not (ROOT / rel_path).is_file():
            errors.append(f"missing required file: {rel_path}")


# 维护 _check_agents_md 函数行为。
def _check_agents_md(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read(".qoder/AGENTS.md")
    if _headings(text) != AGENTS_HEADINGS:
        errors.append(".qoder/AGENTS.md headings do not match required order")
    for heading in AGENTS_HEADINGS[2:]:
        if _bullet_count(_section_text(text, heading)) < 3:
            errors.append(f".qoder/AGENTS.md section has fewer than 3 bullets: {heading}")
    for phrase in ["Qoder", "Protected Path", "Validation", "Forbidden"]:
        if phrase not in text:
            errors.append(f".qoder/AGENTS.md missing required phrase: {phrase}")


# 维护 _check_hook_bindings 函数行为。
def _check_hook_bindings(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read(".qoder/hook-bindings.md")
    if _headings(text) != HOOK_HEADINGS:
        errors.append(".qoder/hook-bindings.md headings do not match required order")
    if LIFECYCLE_TABLE_HEADER not in text:
        errors.append(".qoder/hook-bindings.md missing lifecycle table header")
    for cmd in REQUIRED_HOOK_COMMANDS:
        if cmd not in text:
            errors.append(f".qoder/hook-bindings.md missing hook command: {cmd}")
    for field in ["session_id", "sessionId", "agent_id", "agentId", "tool_input", "toolInput", "file_path", "path", "notebook_path", "command"]:
        if field not in text:
            errors.append(f".qoder/hook-bindings.md missing payload field: {field}")


# 维护 _check_main_agent 函数行为。
def _check_main_agent(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read(".qoder/agents/qoder-main-default.md")
    if _headings(text) != MAIN_HEADINGS:
        errors.append("qoder-main-default.md headings do not match required order")
    for phrase in ["Qoder must read `.qoder/AGENTS.md`", "Use `.qoder/agents/*` descriptions"]:
        if phrase not in text:
            errors.append(f"qoder-main-default.md missing required phrase: {phrase}")


# 维护 _check_specialists 函数行为。
def _check_specialists(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    for path in sorted((ROOT / ".qoder/agents").glob("*.md")):
        if path.name == "qoder-main-default.md" or path.name.startswith("feipi-"):
            continue
        name = path.stem
        text = path.read_text(encoding="utf-8")
        expected = [f"# {name}", *SPECIALIST_HEADINGS]
        if _headings(text) != expected:
            errors.append(f"{path.relative_to(ROOT)} headings do not match specialist contract")
        required_skill = SPECIALIST_SKILLS.get(name)
        if required_skill and required_skill not in text:
            errors.append(f"{path.relative_to(ROOT)} missing shared skill reference: {required_skill}")
        for phrase in RUNTIME_SPECIALIST_PHRASES.get(name, []):
            if phrase not in text:
                errors.append(f"{path.relative_to(ROOT)} missing required reference: {phrase}")


# 维护 _check_manifest 函数行为。
def _check_manifest(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _parse_manifest_text()
    qoder_block_match = re.search(r"(?ms)^  qoder:\n(.*?)(?=^shared_skills:)", text)
    if not qoder_block_match:
        errors.append("manifest missing platforms.qoder block")
        return
    block = qoder_block_match.group(1)
    for phrase in [
        "- .qoder/AGENTS.md",
        "- .qoder/settings.json",
        "- .qoder/settings.local.example.json",
        "- .qoder/hook-bindings.md",
        "agents_dir: .qoder/agents",
        "skills_dir: .qoder/skills",
    ]:
        if phrase not in block:
            errors.append(f"manifest qoder block missing: {phrase}")
    for cmd in REQUIRED_HOOK_COMMANDS:
        if cmd not in block:
            errors.append(f"manifest qoder hooks missing: {cmd}")
        elif not (ROOT / cmd).is_file():
            errors.append(f"manifest qoder hook target missing: {cmd}")
    for directory in [".qoder/agents", ".qoder/skills"]:
        if not (ROOT / directory).is_dir():
            errors.append(f"manifest qoder directory missing: {directory}")


# 维护 _check_skill_registry 函数行为。
def _check_skill_registry(errors: list[str]) -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    text = _read("harness/skill-registry.yaml")
    if "- .qoder/skills" not in text:
        errors.append("skill registry entry_roots missing .qoder/skills")
    for skill in [*SPECIALIST_SKILLS.values(), "skills/authoring/feipi-openspec-orchestrate-change/SKILL.md"]:
        name = skill.split("/")[-2]
        entry = ROOT / ".qoder" / "skills" / name
        if f"- .qoder/skills/{name}" not in text:
            errors.append(f"skill registry missing qoder exposed entry for {name}")
        if not entry.exists():
            errors.append(f"qoder skill entry missing: .qoder/skills/{name}")


# 维护 main 函数行为。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    errors: list[str] = []
    _check_required_files(errors)
    if not errors:
        _check_agents_md(errors)
        _check_hook_bindings(errors)
        _check_settings_json(errors)
        _check_main_agent(errors)
        _check_specialists(errors)
        _check_manifest(errors)
        _check_skill_registry(errors)
    if errors:
        for error in errors:
            print(f"[{GATE_NAME}] FAIL: {error}")
        return 1
    print(f"[{GATE_NAME}] PASS skipped_count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
