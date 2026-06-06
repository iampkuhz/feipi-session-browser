from __future__ import annotations

from dataclasses import dataclass, field
import json
import sys
from typing import Any


# 01. Claude Hook 输入模型
@dataclass
class HookContext:
    """Claude Code hook 输入的结构化视图。"""

    event_name: str
    raw: dict[str, Any] = field(default_factory=dict)
    parse_error: str | None = None

    @property
    def hook_event_name(self) -> str:
        return str(self.raw.get("hook_event_name") or self.event_name)

    @property
    def tool_name(self) -> str:
        return str(self.raw.get("tool_name") or self.raw.get("toolName") or "")

    @property
    def tool_input(self) -> dict[str, Any]:
        value = self.raw.get("tool_input") or self.raw.get("toolInput") or {}
        return value if isinstance(value, dict) else {}

    @property
    def tool_use_id(self) -> str:
        return str(self.raw.get("tool_use_id") or self.raw.get("toolUseId") or "")

    @property
    def command(self) -> str:
        return str(self.tool_input.get("command") or "")

    @property
    def session_id(self) -> str:
        return str(self.raw.get("session_id") or self.raw.get("sessionId") or "")

    @property
    def transcript_path(self) -> str:
        return str(self.raw.get("transcript_path") or self.raw.get("transcriptPath") or "")

    @property
    def cwd(self) -> str:
        return str(self.raw.get("cwd") or self.tool_input.get("cwd") or "")

    @property
    def agent_id(self) -> str:
        return str(self.raw.get("agent_id") or self.raw.get("agentId") or "")

    @property
    def agent_type(self) -> str:
        return str(self.raw.get("agent_type") or self.raw.get("agentType") or "")

    @property
    def candidate_paths(self) -> list[str]:
        """提取 Write/Edit/MultiEdit/NotebookEdit 可能涉及的路径。"""

        candidates: list[str] = []
        for key in ("file_path", "path", "notebook_path"):
            value = self.tool_input.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

        # MultiEdit may provide per-edit paths in addition to top-level file_path.
        edits = self.tool_input.get("edits")
        if isinstance(edits, list):
            for item in edits:
                if isinstance(item, dict):
                    for key in ("file_path", "path", "notebook_path"):
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
    """读取 Claude Code hook stdin；失败时不崩溃，返回带 parse_error 的对象。"""

    if stdin_text is None:
        try:
            stdin_text = sys.stdin.read()
        except Exception as exc:
            return HookContext(event_name=event_name, raw={}, parse_error=f"stdin-read-error: {exc}")

    if not stdin_text.strip():
        return HookContext(event_name=event_name, raw={})

    try:
        parsed = json.loads(stdin_text)
        if not isinstance(parsed, dict):
            return HookContext(event_name=event_name, raw={}, parse_error="stdin-json-not-object")
        return HookContext(event_name=event_name, raw=parsed)
    except Exception as exc:
        return HookContext(event_name=event_name, raw={}, parse_error=f"stdin-json-error: {exc}")


# 03. 自测试
def _self_test() -> None:
    ctx = read_stdin_json("pre-bash", '{"tool_name":"Bash","tool_input":{"command":"git status"}}')
    assert ctx.tool_name == "Bash"
    assert ctx.command == "git status"
    ctx2 = read_stdin_json("post-write", '{"tool_name":"Edit","tool_input":{"file_path":"src/a.py"}}')
    assert ctx2.candidate_paths == ["src/a.py"]
    ctx3 = read_stdin_json("x", "not-json")
    assert ctx3.parse_error


if __name__ == "__main__":
    _self_test()
    print("hook_io self-test PASS")
