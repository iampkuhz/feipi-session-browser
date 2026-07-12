#!/usr/bin/env python3
"""本模块负责检查 Qoder 与其他平台的 runtime 入口对等性。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
GATE_NAME = "qoderRuntimeParity"

from scripts.checks._trigger import (  # noqa: E402
    parse_changed_files,
    skip_if_not_triggered,
)

TRIGGER_PATTERNS = [
    'AGENTS.md',
    'CLAUDE.md',
    '.agents/**',
    '.claude/**',
    '.codex/**',
    '.qoder/**',
    'skills/**',
    'harness/**',
    'scripts/agent_runtime/**/*.py',
    'scripts/hooks/**/*.py',
    'scripts/harness/**/*.py',
    'scripts/harness/**/*.sh',
    'scripts/checks/**/*.py',
]

REQUIRED_FILES = [
    ".qoder/README.md",
    ".qoder/AGENTS.md",
    ".qoder/settings.json",
    ".qoder/settings.local.example.json",
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
        "scripts/agent_runtime/paths.py",
    ]
}

REQUIRED_HOOK_COMMANDS = [
    ".qoder/hooks/session-start.sh",
    ".qoder/hooks/cwd-changed.sh",
    ".qoder/hooks/user-prompt-submit.sh",
    ".qoder/hooks/pre_tool_bootstrap.sh",
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
    ("CwdChanged", ""): ".qoder/hooks/cwd-changed.sh",
    ("UserPromptSubmit", ""): ".qoder/hooks/user-prompt-submit.sh",
    ("PreToolUse", ""): ".qoder/hooks/pre_tool_bootstrap.sh",
    ("PreToolUse", "Bash"): ".qoder/hooks/pre_tool_guard.sh",
    (
        "PreToolUse",
        "Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch",
    ): ".qoder/hooks/pre_write_guard.sh",
    ("PostToolUse", "Bash"): ".qoder/hooks/post_bash_guard.sh",
    (
        "PostToolUse",
        "Write|Edit|MultiEdit|NotebookEdit|apply_patch|ApplyPatch",
    ): ".qoder/hooks/post_tool_guard.sh",
    ("PostToolUseFailure", ""): ".qoder/hooks/tool_failure.sh",
    ("Stop", ""): ".qoder/hooks/stop_check.sh",
    ("StopFailure", ""): ".qoder/hooks/stop_failure.sh",
    ("SessionEnd", ""): ".qoder/hooks/session_end.sh",
}

QODER_WRAPPER_DELEGATES = {
    ".qoder/hooks/session-start.sh": 'run_python_hook qoder session-start "$ROOT"',
    ".qoder/hooks/cwd-changed.sh": 'run_python_hook qoder cwd-changed "$ROOT"',
    ".qoder/hooks/user-prompt-submit.sh": 'run_python_hook qoder user-prompt-submit "$ROOT"',
    ".qoder/hooks/pre_tool_bootstrap.sh": 'run_python_hook qoder pre-tool-bootstrap "$ROOT"',
    ".qoder/hooks/pre_tool_guard.sh": 'run_python_hook qoder pre-bash "$ROOT"',
    ".qoder/hooks/pre_write_guard.sh": 'run_python_hook qoder pre-write "$ROOT"',
    ".qoder/hooks/post_bash_guard.sh": 'run_python_hook qoder post-bash "$ROOT"',
    ".qoder/hooks/post_tool_guard.sh": 'run_python_hook qoder post-write "$ROOT"',
    ".qoder/hooks/tool_failure.sh": 'run_python_hook qoder tool-failure "$ROOT"',
    ".qoder/hooks/stop_check.sh": 'run_stop_hook qoder "$ROOT"',
    ".qoder/hooks/stop_failure.sh": 'run_python_hook qoder stop-failure "$ROOT"',
    ".qoder/hooks/session_end.sh": 'run_python_hook qoder session-end "$ROOT"',
}


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
            if (
                isinstance(hook, dict)
                and hook.get("type") == "command"
                and isinstance(hook.get("command"), str)
            ):
                commands.append(hook["command"])
    return commands


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
        if not any(
            expected in command and "git rev-parse --show-toplevel" in command
            for command in commands
        ):
            suffix = f" matcher={matcher}" if matcher else ""
            errors.append(
                f".qoder/settings.json missing Git-root stable {event}{suffix} binding to {expected}"
            )
    stop_commands = _commands_for(settings, "Stop", "")
    for command in stop_commands:
        if ".qoder/hooks/stop_check.sh" in command:
            stop_hook = settings.get("hooks", {}).get("Stop", [])[0].get("hooks", [])[0]
            if int(stop_hook.get("timeout") or 0) < 1230:
                errors.append(
                    ".qoder/settings.json Stop timeout must exceed required gate timeout buffer"
                )
    try:
        local_example = json.loads(_read(".qoder/settings.local.example.json"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f".qoder/settings.local.example.json parse failed: {exc}")
        return
    if "settings.local.json" not in str(local_example.get("description") or ""):
        errors.append(".qoder/settings.local.example.json must remain local-only guidance")
    if local_example.get("environment") not in ({}, None):
        errors.append(".qoder/settings.local.example.json must not inject Session runtime identity")


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _headings(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.startswith("#")]


def _section_text(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    following = re.search(r"\n## ", text[start + len(heading) :])
    if not following:
        return text[start:]
    return text[start : start + len(heading) + following.start()]


def _bullet_count(section: str) -> int:
    return sum(1 for line in section.splitlines() if line.lstrip().startswith("- "))


def _parse_manifest_text() -> str:
    return _read("harness/agent-runtime.manifest.yaml")


def _check_required_files(errors: list[str]) -> None:
    for rel_path in REQUIRED_FILES:
        if not (ROOT / rel_path).is_file():
            errors.append(f"missing required file: {rel_path}")


def _check_agents_md(errors: list[str]) -> None:
    text = _read(".qoder/AGENTS.md")
    if _headings(text) != AGENTS_HEADINGS:
        errors.append(".qoder/AGENTS.md headings do not match required order")
    for heading in AGENTS_HEADINGS[2:]:
        if _bullet_count(_section_text(text, heading)) < 3:
            errors.append(f".qoder/AGENTS.md section has fewer than 3 bullets: {heading}")
    for phrase in ["Qoder", "Protected Path", "Validation", "Forbidden"]:
        if phrase not in text:
            errors.append(f".qoder/AGENTS.md missing required phrase: {phrase}")


# 校验 Qoder 脚本只作为共享 hook runtime 的薄包装层。
def _check_hook_wrappers(errors: list[str]) -> None:
    """校验 Qoder 脚本只作为共享 hook runtime 的薄包装层。"""
    shared_source = 'source "$ROOT/scripts/harness/hook-common.sh"'
    forbidden_logic = (
        "sessionctl.py",
        "scripts/agent_runtime/hook_entry.py",
        "git worktree",
        "rm -",
    )
    for rel_path, delegate in QODER_WRAPPER_DELEGATES.items():
        path = ROOT / rel_path
        if not path.is_file():
            errors.append(f"missing Qoder hook wrapper: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        if shared_source not in text:
            errors.append(f"Qoder hook wrapper does not source shared runtime: {rel_path}")
        if text.count(delegate) != 1:
            errors.append(
                f"Qoder hook wrapper does not delegate exactly once via {delegate}: {rel_path}"
            )
        for phrase in forbidden_logic:
            if phrase in text:
                errors.append(
                    f"Qoder hook wrapper contains duplicated runtime logic ({phrase}): {rel_path}"
                )


def _check_main_agent(errors: list[str]) -> None:
    text = _read(".qoder/agents/qoder-main-default.md")
    if _headings(text) != MAIN_HEADINGS:
        errors.append("qoder-main-default.md headings do not match required order")
    for phrase in ["Qoder must read `.qoder/AGENTS.md`", "Use `.qoder/agents/*` descriptions"]:
        if phrase not in text:
            errors.append(f"qoder-main-default.md missing required phrase: {phrase}")


def _check_specialists(errors: list[str]) -> None:
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
            errors.append(
                f"{path.relative_to(ROOT)} missing shared skill reference: {required_skill}"
            )
        for phrase in RUNTIME_SPECIALIST_PHRASES.get(name, []):
            if phrase not in text:
                errors.append(f"{path.relative_to(ROOT)} missing required reference: {phrase}")


def _check_manifest(errors: list[str]) -> None:
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


def _check_skill_registry(errors: list[str]) -> None:
    """执行 `_check_skill_registry` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
    text = _read("harness/skill-registry.yaml")
    if "- .qoder/skills" not in text:
        errors.append("skill registry entry_roots missing .qoder/skills")
    for skill in [
        *SPECIALIST_SKILLS.values(),
        "skills/authoring/feipi-openspec-orchestrate-change/SKILL.md",
    ]:
        name = skill.split("/")[-2]
        entry = ROOT / ".qoder" / "skills" / name
        if f"- .qoder/skills/{name}" not in text:
            errors.append(f"skill registry missing qoder exposed entry for {name}")
        if not entry.exists():
            errors.append(f"qoder skill entry missing: .qoder/skills/{name}")


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
    _check_required_files(errors)
    if not errors:
        _check_agents_md(errors)
        _check_settings_json(errors)
        _check_hook_wrappers(errors)
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
