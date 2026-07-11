"""解析 Claude Code hook stdin，并返回安全的结构化 context。"""

from __future__ import annotations

import json
import os
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
    empty_input: bool = False

    # 维护 _raw_string 函数行为。
    def _raw_string(self, *keys: str) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        for key in keys:
            value = self.raw.get(key)
            if isinstance(value, str) and value:
                return value
        return ''

    # 维护 _tool_string 函数行为。
    def _tool_string(self, *keys: str) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        tool_input = self.tool_input
        for key in keys:
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                return value
        return self._raw_string(*keys)

    # 返回 hook event name；缺失时使用 CLI event label。
    @property
    # 维护 hook_event_name 函数行为。
    def hook_event_name(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return str(self.raw.get('hook_event_name') or self.event_name)

    # 返回触发 hook 的 tool name。
    @property
    # 维护 tool_name 函数行为。
    def tool_name(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return self._raw_string('tool_name', 'toolName')

    # 返回触发 tool 的输入对象；缺失时返回空映射。
    @property
    # 维护 tool_input 函数行为。
    def tool_input(self) -> dict[str, Any]:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        value = self.raw.get('tool_input') or self.raw.get('toolInput') or {}
        return value if isinstance(value, dict) else {}

    # 返回用于关联 evidence 的 tool-use id。
    @property
    # 维护 tool_use_id 函数行为。
    def tool_use_id(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return str(self.raw.get('tool_use_id') or self.raw.get('toolUseId') or '')

    # 返回 pre-bash hook 中的 Bash 命令。
    @property
    # 维护 command 函数行为。
    def command(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return self._tool_string('command')

    # 返回用于 evidence 隔离的 session id。
    @property
    # 维护 session_id 函数行为。
    def session_id(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return self._raw_string('session_id', 'sessionId')


    # 返回当前运行 id。
    @property
    def run_id(self) -> str:
        """返回：
            当前 hook 输入中的运行 id。
        """
        return self._raw_string('run_id', 'runId')

    # 返回当前任务 id。
    @property
    def task_id(self) -> str:
        """返回：
            当前 hook 输入中的任务 id。
        """
        return self._raw_string('task_id', 'taskId')

    # 返回当前 worktree id。
    @property
    def worktree_id(self) -> str:
        """返回：
            当前 hook 输入中的 worktree id。
        """
        return self._raw_string('worktree_id', 'worktreeId')

    # 返回当前 turn id。
    @property
    def turn_id(self) -> str:
        """返回：
            当前 hook 输入中的 turn id。
        """
        return self._raw_string('turn_id', 'turnId')

    # 判断 Stop hook 是否已激活。
    @property
    def stop_hook_active(self) -> bool:
        """返回：
            Stop hook 激活时返回 true，否则返回 false。
        """
        value = self.raw.get('stop_hook_active')
        if value is None:
            value = self.raw.get('stopHookActive')
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'on'}
        return False

    # 返回 Claude hook 输入中的 transcript 路径。
    @property
    # 维护 transcript_path 函数行为。
    def transcript_path(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return str(self.raw.get('transcript_path') or self.raw.get('transcriptPath') or '')

    # 返回 hook event 的工作目录。
    @property
    # 维护 cwd 函数行为。
    def cwd(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return str(
            self.raw.get('cwd')
            or self.raw.get('workingDirectory')
            or self.tool_input.get('cwd')
            or self.tool_input.get('workingDirectory')
            or os.environ.get('FEIPI_HOOK_CWD')
            or ''
        )

    # 返回 hook event 中的 agent id。
    @property
    # 维护 agent_id 函数行为。
    def agent_id(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return self._raw_string('agent_id', 'agentId')

    # 返回 hook event 中的 agent type。
    @property
    # 维护 agent_type 函数行为。
    def agent_type(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return str(self.raw.get('agent_type') or self.raw.get('agentType') or '')

    # 返回 hook event 中的 agent client 名称。
    @property
    # 维护 agent_client 函数行为。
    def agent_client(self) -> str:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        return self._raw_string('agent_client', 'agentClient', 'client')

    # 提取写入类 hook payload 中的候选路径并保序去重。
    @property
    # 维护 candidate_paths 函数行为。
    def candidate_paths(self) -> list[str]:
        """参数：
            *args: 当前函数使用的输入参数。
    
        返回：
            当前函数计算或校验结果。
        """
        candidates: list[str] = []
        for key in ('file_path', 'path', 'notebook_path'):
            # 从单文件写入类 payload 中读取候选路径。
            value = self.tool_input.get(key)
            if not isinstance(value, str) or not value:
                value = self.raw.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

        edits = self.tool_input.get('edits') or self.raw.get('edits')
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
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if stdin_text is None:
        try:
            stdin_text = sys.stdin.read()
        except Exception as exc:
            return HookContext(
                event_name=event_name, raw={}, parse_error=f'stdin-read-error: {exc}'
            )

    if not stdin_text.strip():
        return HookContext(event_name=event_name, raw={}, empty_input=True)

    try:
        parsed = json.loads(stdin_text)
        if not isinstance(parsed, dict):
            return HookContext(event_name=event_name, raw={}, parse_error='stdin-json-not-object')
        return HookContext(event_name=event_name, raw=parsed)
    except Exception as exc:
        return HookContext(event_name=event_name, raw={}, parse_error=f'stdin-json-error: {exc}')


# 运行脚本自测试场景。
def _self_test() -> None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
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
