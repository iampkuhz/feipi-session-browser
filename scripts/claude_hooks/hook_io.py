"""Parse Claude Code hook stdin into a safe structured context.

Every hook entry point reads a JSON object from stdin. This module normalizes snake_case
and camelCase fields, extracts tool inputs, and converts malformed input into a context
with ``parse_error`` instead of raising, so hooks can report controlled PASS or BLOCK
outcomes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any


# 01. Claude Hook 输入模型
@dataclass
class HookContext:
    """Structured view of one Claude Code hook input event.

    Attributes:
        event_name: Event label supplied by the hook wrapper.
        raw: Parsed JSON object from hook stdin.
        parse_error: Parse failure text, or ``None`` when stdin was valid.
    """

    event_name: str
    raw: dict[str, Any] = field(default_factory=dict)
    parse_error: str | None = None

    @property
    def hook_event_name(self) -> str:
        """Return Claude's hook event name, falling back to the CLI event label."""
        return str(self.raw.get('hook_event_name') or self.event_name)

    @property
    def tool_name(self) -> str:
        """Return the tool name that triggered the hook event."""
        return str(self.raw.get('tool_name') or self.raw.get('toolName') or '')

    @property
    def tool_input(self) -> dict[str, Any]:
        """Return the triggering tool input object or an empty mapping."""
        value = self.raw.get('tool_input') or self.raw.get('toolInput') or {}
        return value if isinstance(value, dict) else {}

    @property
    def tool_use_id(self) -> str:
        """Return the tool-use id used to correlate hook evidence."""
        return str(self.raw.get('tool_use_id') or self.raw.get('toolUseId') or '')

    @property
    def command(self) -> str:
        """Return the Bash command from a pre-bash hook input."""
        return str(self.tool_input.get('command') or '')

    @property
    def session_id(self) -> str:
        """Return the Claude session id for per-session evidence grouping."""
        return str(self.raw.get('session_id') or self.raw.get('sessionId') or '')

    @property
    def transcript_path(self) -> str:
        """Return the transcript path supplied by Claude hook input."""
        return str(self.raw.get('transcript_path') or self.raw.get('transcriptPath') or '')

    @property
    def cwd(self) -> str:
        """Return the event working directory from hook or tool input."""
        return str(self.raw.get('cwd') or self.tool_input.get('cwd') or '')

    @property
    def agent_id(self) -> str:
        """Return the subagent id when the hook event includes one."""
        return str(self.raw.get('agent_id') or self.raw.get('agentId') or '')

    @property
    def agent_type(self) -> str:
        """Return the subagent type when the hook event includes one."""
        return str(self.raw.get('agent_type') or self.raw.get('agentType') or '')

    @property
    def candidate_paths(self) -> list[str]:
        """Extract unique candidate paths from write-oriented hook inputs.

        Returns:
            Ordered paths from Write, Edit, MultiEdit, and NotebookEdit tool payloads.
        """
        candidates: list[str] = []
        for key in ('file_path', 'path', 'notebook_path'):
            value = self.tool_input.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

        # MultiEdit may provide per-edit paths in addition to top-level file_path.
        edits = self.tool_input.get('edits')
        if isinstance(edits, list):
            for item in edits:
                if isinstance(item, dict):
                    for key in ('file_path', 'path', 'notebook_path'):
                        value = item.get(key)
                        if isinstance(value, str) and value:
                            candidates.append(value)

        # 去重但保序。
        seen: set[str] = set()
        result: list[str] = []
        for item in candidates:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result


# 02. stdin JSON 读取
def read_stdin_json(event_name: str, stdin_text: str | None = None) -> HookContext:
    """Read Claude hook stdin without crashing on malformed JSON.

    Args:
        event_name: Hook event label supplied by the CLI wrapper.
        stdin_text: Optional test fixture text. When omitted, stdin is read directly.

    Returns:
        ``HookContext`` containing parsed input, or ``parse_error`` when input cannot be
        read or parsed. Parse failures are reported in evidence rather than raised.
    """
    if stdin_text is None:
        try:
            stdin_text = sys.stdin.read()
        except Exception as exc:
            return HookContext(
                event_name=event_name, raw={}, parse_error=f'stdin-read-error: {exc}'
            )

    if not stdin_text.strip():
        return HookContext(event_name=event_name, raw={})

    try:
        parsed = json.loads(stdin_text)
        if not isinstance(parsed, dict):
            return HookContext(event_name=event_name, raw={}, parse_error='stdin-json-not-object')
        return HookContext(event_name=event_name, raw=parsed)
    except Exception as exc:
        return HookContext(event_name=event_name, raw={}, parse_error=f'stdin-json-error: {exc}')


# 03. 自测试
def _self_test() -> None:
    """Run local assertions for hook stdin parsing."""
    ctx = read_stdin_json('pre-bash', '{"tool_name":"Bash","tool_input":{"command":"git status"}}')
    assert ctx.tool_name == 'Bash'
    assert ctx.command == 'git status'
    ctx2 = read_stdin_json(
        'post-write', '{"tool_name":"Edit","tool_input":{"file_path":"src/a.py"}}'
    )
    assert ctx2.candidate_paths == ['src/a.py']
    ctx3 = read_stdin_json('x', 'not-json')
    assert ctx3.parse_error


if __name__ == '__main__':
    _self_test()
    print('hook_io self-test PASS')
