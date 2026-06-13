"""Claude Code request tool definition resolver.

Claude Code JSONL stores the selected main agent name as an ``agent-setting``
event, but it does not persist the request-side ``tools`` schema array.  This
module resolves the current Claude agent/subagent to its ``tools:`` frontmatter
definition and falls back to the built-in Claude Code tool registry when a
custom definition cannot be proven.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from session_browser.attribution.agents.claude_code_tool_schemas import (
    ALL_CLAUDE_CODE_TOOLS,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaudeCodeAvailableTools:
    tools: list[str]
    source: str
    agent_name: str = ""
    definition_path: str = ""
    reason: str = ""


def parse_agent_tools_from_frontmatter(text: str) -> list[str] | None:
    """Parse a Claude agent markdown file's YAML frontmatter ``tools:`` field."""
    frontmatter = _frontmatter(text)
    if frontmatter is None:
        return None

    tools_match = re.search(r"^tools:\s*(.+)$", frontmatter, re.MULTILINE)
    if not tools_match:
        return None

    tools_str = tools_match.group(1).strip()
    if not tools_str:
        return None

    paren_re = re.compile(r"(\w+)\([^)]*\)")
    tools: list[str] = [pm.group(1) for pm in paren_re.finditer(tools_str)]

    remaining = paren_re.sub("", tools_str)
    for part in remaining.split(","):
        tool = part.strip()
        if tool:
            tools.append(tool)

    return sorted(set(tools)) if tools else None


def parse_agent_name_from_frontmatter(text: str) -> str:
    """Return the frontmatter ``name:`` value when present."""
    frontmatter = _frontmatter(text)
    if frontmatter is None:
        return ""
    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    if not name_match:
        return ""
    return name_match.group(1).strip().strip("\"'")


def detect_main_agent_setting(
    session_file: str | Path | None,
    *,
    call_timestamp: str | None = None,
) -> str:
    """Read the selected main agent name from a Claude Code session JSONL file."""
    if not session_file:
        return ""

    path = Path(session_file)
    if not path.is_file():
        return ""

    call_ts = _parse_timestamp(call_timestamp or "")
    selected = ""
    fallback = ""

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("type") != "agent-setting":
                    continue

                agent_name = str(event.get("agentSetting") or "").strip()
                if not agent_name:
                    continue
                fallback = agent_name

                event_ts = _parse_timestamp(str(event.get("timestamp") or ""))
                if call_ts and event_ts and event_ts > call_ts:
                    break
                selected = agent_name
    except (OSError, PermissionError) as exc:
        logger.debug("Cannot read Claude Code session file %s: %s", path, exc)
        return ""

    return selected or fallback


def read_agent_definition_tools(
    agent_name: str,
    project_dir: str | Path | None,
    *,
    home_dir: str | Path | None = None,
) -> tuple[list[str], str]:
    """Resolve one agent's explicit builtin tool list from project/global files."""
    if not agent_name:
        return [], ""

    for candidate in _agent_definition_candidates(agent_name, project_dir, home_dir):
        try:
            if not candidate.is_file():
                continue
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            logger.debug("Cannot read Claude agent definition %s: %s", candidate, exc)
            continue

        tools = parse_agent_tools_from_frontmatter(text)
        if not tools:
            continue
        valid = sorted(tool for tool in tools if tool in ALL_CLAUDE_CODE_TOOLS)
        if valid:
            return valid, str(candidate)

    return [], ""


def resolve_claude_code_available_tools(
    *,
    project_dir: str | Path | None,
    session_file: str | Path | None = None,
    subagent_type: str | None = None,
    call_timestamp: str | None = None,
    home_dir: str | Path | None = None,
) -> ClaudeCodeAvailableTools:
    """Resolve request-side Claude Code tool schemas for one main/subagent call."""
    target_agent = (subagent_type or "").strip()
    if not target_agent:
        target_agent = detect_main_agent_setting(
            session_file,
            call_timestamp=call_timestamp,
        )

    if target_agent:
        tools, definition_path = read_agent_definition_tools(
            target_agent,
            project_dir,
            home_dir=home_dir,
        )
        if tools:
            return ClaudeCodeAvailableTools(
                tools=tools,
                source="agent_definition",
                agent_name=target_agent,
                definition_path=definition_path,
                reason=f"resolved tools from agent definition for {target_agent}",
            )

    reason = "no custom agent setting found"
    if subagent_type:
        reason = f"subagent definition not found or has no explicit tools: {subagent_type}"
    elif target_agent:
        reason = f"agent definition not found or has no explicit tools: {target_agent}"

    return ClaudeCodeAvailableTools(
        tools=list(ALL_CLAUDE_CODE_TOOLS),
        source="default_builtin",
        agent_name=target_agent,
        definition_path="",
        reason=reason,
    )


def _frontmatter(text: str) -> str | None:
    match = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None
    return match.group(1)


def _agent_definition_candidates(
    agent_name: str,
    project_dir: str | Path | None,
    home_dir: str | Path | None,
) -> list[Path]:
    candidates: list[Path] = []
    if project_dir:
        candidates.append(Path(project_dir) / ".claude" / "agents" / f"{agent_name}.md")

    home = Path(home_dir) if home_dir else Path.home()
    candidates.append(home / ".claude" / "agents" / f"{agent_name}.md")
    return candidates


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
