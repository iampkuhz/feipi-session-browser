"""解析 Claude Code hook stdin，并返回安全的结构化 context。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any


# 01. Claude Hook 输入模型
@dataclass
class HookContext:
    """保存 HookContext 的结构化数据。

    属性：
        event_name: hook wrapper 提供的 event label。
        raw: stdin 解析出的 JSON 对象。
        parse_error: 解析失败信息；输入有效时为 None。
    """

    event_name: str
    raw: dict[str, Any] = field(default_factory=dict)
    parse_error: str | None = None

    # 返回 hook event name；缺失时使用 CLI event label。
    @property
    def hook_event_name(self) -> str:
        """返回：
            hook event name 字符串。
        """
        return str(self.raw.get('hook_event_name') or self.event_name)

    # 返回触发 hook 的 tool name。
    @property
    def tool_name(self) -> str:
        """返回：
            tool name 字符串。
        """
        return str(self.raw.get('tool_name') or self.raw.get('toolName') or '')

    # 返回触发 tool 的输入对象；缺失时返回空映射。
    @property
    def tool_input(self) -> dict[str, Any]:
        """返回：
            结果映射。
        """
        value = self.raw.get('tool_input') or self.raw.get('toolInput') or {}
        return value if isinstance(value, dict) else {}

    # 返回用于关联 evidence 的 tool-use id。
    @property
    def tool_use_id(self) -> str:
        """返回：
            tool-use id 字符串。
        """
        return str(self.raw.get('tool_use_id') or self.raw.get('toolUseId') or '')

    # 返回 pre-bash hook 中的 Bash 命令。
    @property
    def command(self) -> str:
        """返回：
            Bash 命令字符串。
        """
        return str(self.tool_input.get('command') or '')

    # 返回用于 evidence 隔离的 session id。
    @property
    def session_id(self) -> str:
        """返回：
            session id 字符串。
        """
        return str(self.raw.get('session_id') or self.raw.get('sessionId') or '')

    # 返回 Claude hook 输入中的 transcript 路径。
    @property
    def transcript_path(self) -> str:
        """返回：
            transcript 路径字符串。
        """
        return str(self.raw.get('transcript_path') or self.raw.get('transcriptPath') or '')

    # 返回 hook event 的工作目录。
    @property
    def cwd(self) -> str:
        """返回：
            工作目录字符串。
        """
        return str(self.raw.get('cwd') or self.tool_input.get('cwd') or '')

    # 返回 hook event 中的 agent id。
    @property
    def agent_id(self) -> str:
        """返回：
            agent id 字符串。
        """
        return str(self.raw.get('agent_id') or self.raw.get('agentId') or '')

    # 返回 hook event 中的 agent type。
    @property
    def agent_type(self) -> str:
        """返回：
            agent type 字符串。
        """
        return str(self.raw.get('agent_type') or self.raw.get('agentType') or '')

    # 返回 hook event 中的 agent client 名称。
    @property
    def agent_client(self) -> str:
        """返回：
            agent client 名称。
        """
        return str(
            self.raw.get('agent_client')
            or self.raw.get('agentClient')
            or self.raw.get('client')
            or ''
        )

    # 提取写入类 hook payload 中的候选路径并保序去重。
    @property
    def candidate_paths(self) -> list[str]:
        """返回：
            写入类 tool payload 中出现的候选路径列表。
        """
        candidates: list[str] = []
        for key in ('file_path', 'path', 'notebook_path'):
            # 从单文件写入类 payload 中读取候选路径。
            value = self.tool_input.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

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


# 读取stdin JSON。
def read_stdin_json(event_name: str, stdin_text: str | None = None) -> HookContext:
    """参数：
        event_name: hook event 标签。
        stdin_text: 测试传入的 stdin 文本；为空时读取真实 stdin。

    返回：
        解析后的 HookContext；失败时携带 parse_error。
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


# 运行脚本自测试场景。
def _self_test() -> None:
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
