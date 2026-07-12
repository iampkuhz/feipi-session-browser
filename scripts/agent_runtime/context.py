"""解析三平台 Hook 输入并读取当前 OpenSpec change。

本模块只建立不可变的请求上下文和 active-change 查询结果；不决定策略、
不写 evidence，也不触发 Session bootstrap。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.agent_runtime.paths import RepoPaths


PAYLOAD_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    'session_id': ('session_id', 'sessionId'),
    'agent_id': ('agent_id', 'agentId'),
    'agent_client': ('agent_client', 'agentClient', 'client'),
    'cwd': ('cwd', 'workingDirectory', 'working_directory', 'workspaceRoot', 'workspace_root'),
    'client_surface': ('client_surface', 'clientSurface', 'surface', 'platform'),
    'parent_run_id': ('parent_run_id', 'parentRunId'),
}


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

    def _raw_string(self, *keys: str) -> str:
        for key in keys:
            value = self.raw.get(key)
            if isinstance(value, str) and value:
                return value
        return ''

    # 按共享 alias 表读取平台字段。
    def _aliased_string(self, field_name: str) -> str:
        """参数：
            field_name: alias 表中的统一字段名。

        返回：
            payload 中首个非空 alias 值。
        """

        return self._raw_string(*PAYLOAD_FIELD_ALIASES[field_name])

    def _tool_string(self, *keys: str) -> str:
        tool_input = self.tool_input
        for key in keys:
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                return value
        return self._raw_string(*keys)

    # 返回 hook event name；缺失时使用 CLI event label。
    @property
    def hook_event_name(self) -> str:
        """执行 `hook_event_name` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return str(self.raw.get('hook_event_name') or self.event_name)

    # 返回触发 hook 的 tool name。
    @property
    def tool_name(self) -> str:
        """执行 `tool_name` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return self._raw_string('tool_name', 'toolName')

    # 返回触发 tool 的输入对象；缺失时返回空映射。
    @property
    def tool_input(self) -> dict[str, Any]:
        """执行 `tool_input` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        value = self.raw.get('tool_input') or self.raw.get('toolInput') or {}
        return value if isinstance(value, dict) else {}

    # 返回用于关联 evidence 的 tool-use id。
    @property
    def tool_use_id(self) -> str:
        """执行 `tool_use_id` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return str(self.raw.get('tool_use_id') or self.raw.get('toolUseId') or '')

    # 返回 pre-bash hook 中的 Bash 命令。
    @property
    def command(self) -> str:
        """执行 `command` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return self._tool_string('command')

    # 返回用于 evidence 隔离的 session id。
    @property
    def session_id(self) -> str:
        """执行 `session_id` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return self._aliased_string('session_id')

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
    def transcript_path(self) -> str:
        """执行 `transcript_path` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return str(self.raw.get('transcript_path') or self.raw.get('transcriptPath') or '')

    # 返回 hook event 的工作目录。
    @property
    def cwd(self) -> str:
        """执行 `cwd` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return str(
            self._aliased_string('cwd')
            or self.tool_input.get('cwd')
            or self.tool_input.get('workingDirectory')
            or os.environ.get('FEIPI_HOOK_CWD')
            or ''
        )

    # 返回 hook event 中的 agent id。
    @property
    def agent_id(self) -> str:
        """执行 `agent_id` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return self._aliased_string('agent_id')

    # 返回 hook event 中的 agent type。
    @property
    def agent_type(self) -> str:
        """执行 `agent_type` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return str(self.raw.get('agent_type') or self.raw.get('agentType') or '')

    # 返回 hook event 中的 agent client 名称。
    @property
    def agent_client(self) -> str:
        """执行 `agent_client` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
        return self._aliased_string('agent_client')

    # 返回 payload 显式声明的客户端 surface。
    @property
    def client_surface(self) -> str:
        """返回：
        客户端 surface；该值不用于推断路径。
        """

        return self._aliased_string('client_surface')

    # 返回显式 subagent 父 run 标识。
    @property
    def parent_run_id(self) -> str:
        """返回：
        subagent 父 run 标识。
        """

        return self._aliased_string('parent_run_id')

    # 提取写入类 hook payload 中的候选路径并保序去重。
    @property
    def candidate_paths(self) -> list[str]:
        """执行 `candidate_paths` 对应的公开仓库能力；遵守模块定义的边界与失败语义。"""
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


# 读取标准输入中的 JSON；空输入按空对象处理。
def read_stdin_json(event_name: str, stdin_text: str | None = None) -> HookContext:
    """读取标准输入中的 JSON；空输入按空对象处理。"""
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


# 维护默认 change id。
def default_change_id() -> str:
    """返回：
    default change id 字符串。
    """
    return 'adhoc-' + datetime.now(timezone.utc).strftime('%Y%m%d')


# 读取JSON。
def _read_json(path: Path) -> dict[str, Any]:
    """参数：
        path: JSON 文件到读取。

    返回：
        结果映射。
    """
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


# 读取active change。
def read_active_change(paths: RepoPaths) -> dict[str, Any]:
    """参数：
        paths: 待检查的路径列表。

    返回：
        结果映射。
    """
    for candidate in paths.active_change_candidates:
        data = _read_json(candidate)
        if data:
            return data
    return {'changeId': default_change_id(), 'source': 'default'}


# 维护当前 change id。
def current_change_id(paths: RepoPaths) -> str:
    """参数：
        paths: 待检查的路径列表。

    返回：
        current change id 字符串。
    """
    data = read_active_change(paths)
    return str(data.get('changeId') or data.get('change_id') or default_change_id())
