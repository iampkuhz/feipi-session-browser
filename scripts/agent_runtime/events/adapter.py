"""本模块负责把 Claude、Codex 与 Qoder payload 归一为 Session bootstrap 请求。

本模块只允许声明平台字段、别名和事件差异；Session 状态与路径策略不在这里实现。

不负责平台 Hook 配置；由共享 dispatcher 或 Stop runtime 调用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

UNVERIFIED = "UNVERIFIED"

# 平台配置只能向共享 dispatcher 传递这些稳定 runtime event label。
RUNTIME_EVENTS = frozenset(
    {
        'config-change',
        'cwd-changed',
        'post-bash',
        'post-tool',
        'post-write',
        'pre-bash',
        'pre-tool',
        'pre-tool-bootstrap',
        'pre-write',
        'session-end',
        'session-start',
        'stop',
        'stop-failure',
        'subagent-start',
        'tool-failure',
        'user-prompt-submit',
    }
)


class HookPayload(Protocol):
    """Adapter 只依赖的最小 hook context contract。"""

    event_name: str
    raw: dict[str, Any]

    # 返回平台 payload 中的 Hook 事件名。
    @property
    def hook_event_name(self) -> str:
        """返回：
        Hook 事件名。
        """
        ...

    # 返回平台 payload 中的 Session 标识。
    @property
    def session_id(self) -> str:
        """返回：
        Session 标识。
        """
        ...

    # 返回平台已选 checkout 的工作目录。
    @property
    def cwd(self) -> str:
        """返回：
        当前工作目录。
        """
        ...

    # 返回 dispatcher 声明的客户端名称。
    @property
    def agent_client(self) -> str:
        """返回：
        客户端名称。
        """
        ...

    # 返回 payload 显式声明的客户端 surface。
    @property
    def client_surface(self) -> str:
        """返回：
        客户端 surface。
        """
        ...

    # 返回 subagent 继承的父 run 标识。
    @property
    def parent_run_id(self) -> str:
        """返回：
        父 run 标识。
        """
        ...


@dataclass(frozen=True)
class PlatformAdapter:
    """平台之间仅保留 payload/事件差异，不承载 Session 业务逻辑。"""

    surface: str
    client: str
    checkout_creator: str
    bootstrap_events: frozenset[str]
    aliases: tuple[str, ...]
    verification: str = UNVERIFIED


@dataclass(frozen=True)
class BootstrapRequest:
    """调用 ``bootstrap_session`` 所需的统一参数。"""

    adapter: PlatformAdapter
    client: str
    session_id: str
    cwd: str
    hook_event: str
    checkout_creator: str
    payload_hints: Mapping[str, Any]
    parent_run_id: str = ""


class HookAdapterError(ValueError):
    """表示 payload 无法安全转换为 bootstrap 请求。"""


PLATFORM_ADAPTERS = (
    PlatformAdapter(
        surface="codex-app",
        client="codex",
        checkout_creator="codex",
        bootstrap_events=frozenset({"SessionStart", "UserPromptSubmit", "PreToolUse"}),
        aliases=("codex-app", "codex_app", "codex app"),
    ),
    PlatformAdapter(
        surface="codex-cli",
        client="codex",
        checkout_creator="codex",
        bootstrap_events=frozenset({"SessionStart", "UserPromptSubmit", "PreToolUse"}),
        aliases=("codex-cli", "codex_cli", "codex cli", "codex"),
    ),
    PlatformAdapter(
        surface="claude-code-cli",
        client="claude",
        checkout_creator="claude",
        bootstrap_events=frozenset({"SessionStart", "CwdChanged"}),
        aliases=("claude-code-cli", "claude_code_cli", "claude cli", "claude"),
    ),
    PlatformAdapter(
        surface="qoder-cli",
        client="qoder",
        checkout_creator="qoder",
        bootstrap_events=frozenset({"SessionStart", "CwdChanged", "PreToolUse"}),
        aliases=("qoder-cli", "qoder_cli", "qodercli"),
    ),
    PlatformAdapter(
        surface="qoder-client",
        client="qoder",
        checkout_creator="qoder",
        bootstrap_events=frozenset(
            {"SessionStart", "UserPromptSubmit", "PreToolUse", "CwdChanged"}
        ),
        aliases=("qoder-client", "qoder_client", "qoder ide", "qoder jb", "qoder"),
    ),
)


# 将平台别名规范化为可比较 token。
def _token(value: str) -> str:
    """参数：
        value: 原始平台别名。

    返回：
        去除分隔符后的小写 token。
    """
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


_ADAPTER_BY_ALIAS = {
    _token(alias): adapter
    for adapter in PLATFORM_ADAPTERS
    for alias in (adapter.surface, *adapter.aliases)
}
_DEFAULT_BY_CLIENT = {
    # 无 surface 的 Codex payload 无法证明来自受控 CLI launcher；按 App 能力缺口
    # fail closed，禁止把仓库 fixture 冒充真实 host lifecycle 证明。
    "codex": _ADAPTER_BY_ALIAS[_token("codex-app")],
    "claude": _ADAPTER_BY_ALIAS[_token("claude-code-cli")],
    "qoder": _ADAPTER_BY_ALIAS[_token("qoder-cli")],
}

_EVENT_ALIASES = {
    "sessionstart": "SessionStart",
    "userpromptsubmit": "UserPromptSubmit",
    "cwdchanged": "CwdChanged",
    "pretooluse": "PreToolUse",
    "pretool": "PreToolUse",
    "pretoolbootstrap": "PreToolUse",
    # 平台配置按工具类型拆分 PreToolUse，adapter 仍统一为同一事件。
    "prebash": "PreToolUse",
    "prewrite": "PreToolUse",
}

_BASH_TOOL_NAMES = frozenset({'bash', 'shell', 'execcommand', 'command'})
_WRITE_TOOL_NAMES = frozenset({'write', 'edit', 'multiedit', 'notebookedit', 'applypatch', 'patch'})


def normalize_tool_name(value: str) -> str:
    """把平台工具名压缩为无分隔符 token，供共享策略入口唯一分类。"""

    return re.sub(r'[^a-z0-9]+', '', value.rsplit('.', 1)[-1].lower())


def tool_handler_kind(value: str) -> str:
    """返回 ``bash``、``write`` 或 ``observe``，未知工具不得误判为 mutation。"""

    normalized = normalize_tool_name(value)
    if normalized in _BASH_TOOL_NAMES:
        return 'bash'
    if normalized in _WRITE_TOOL_NAMES:
        return 'write'
    return 'observe'


# 按优先级将 event label 转为统一事件名。
def canonical_hook_event(*values: str) -> str:
    """参数：
        values: 按权威顺序排列的原始事件名。

    返回：
        统一事件名；首个非空值无法识别时返回空字符串。
    """

    for value in values:
        if value.strip():
            return _EVENT_ALIASES.get(_token(value), "")
    return ""


# 根据显式 surface 或 dispatcher client 选择薄 adapter。
def resolve_platform_adapter(
    ctx: HookPayload,
    *,
    wrapper_client: str = "",
    hook_event: str = "",
) -> PlatformAdapter | None:
    """参数：
        ctx: 平台 Hook payload。
        wrapper_client: dispatcher 明确声明的客户端。
        hook_event: 统一后的 Hook 事件名。

    返回：
        匹配的 adapter；无法识别时返回 None。
    """

    client = wrapper_client.strip().lower() or ctx.agent_client.strip().lower()
    surface = ctx.client_surface
    adapter = _ADAPTER_BY_ALIAS.get(_token(surface)) if surface else None
    if adapter and client and client != adapter.client:
        raise HookAdapterError(
            f"hook surface {adapter.surface} conflicts with dispatcher client {client}"
        )
    if adapter:
        return adapter
    if client == "qoder" and hook_event in {"UserPromptSubmit", "PreToolUse"}:
        return _ADAPTER_BY_ALIAS[_token("qoder-client")]
    return _DEFAULT_BY_CLIENT.get(client)


# 为会话生命周期 Hook 构造统一 bootstrap 请求。
def build_bootstrap_request(
    ctx: HookPayload,
    *,
    wrapper_client: str = "",
) -> BootstrapRequest | None:
    """参数：
        ctx: 平台 Hook payload。
        wrapper_client: dispatcher 明确声明的客户端。

    返回：
        统一 bootstrap 请求；当前事件不触发 bootstrap 时返回 None。
    """

    hook_event = canonical_hook_event(ctx.event_name, ctx.hook_event_name)
    adapter = resolve_platform_adapter(
        ctx,
        wrapper_client=wrapper_client,
        hook_event=hook_event,
    )
    if not adapter or hook_event not in adapter.bootstrap_events:
        return None
    if not ctx.session_id:
        raise HookAdapterError(f"{hook_event} payload missing session id")
    if not ctx.cwd:
        raise HookAdapterError(f"{hook_event} payload missing cwd")
    return BootstrapRequest(
        adapter=adapter,
        client=adapter.client,
        session_id=ctx.session_id,
        cwd=ctx.cwd,
        hook_event=hook_event,
        checkout_creator=adapter.checkout_creator,
        payload_hints=dict(ctx.raw),
        parent_run_id=ctx.parent_run_id,
    )
