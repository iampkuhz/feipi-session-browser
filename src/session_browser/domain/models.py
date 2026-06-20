"""session-browser 领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone


# 说明：─── Token types ───────────────────────────────────────────────────────────


class TokenPrecision:
    EXACT = "exact"
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNKNOWN = "unavailable"
    # 内部精度/source 细分；UI 展示前会归一到 attribution.contracts 的公开枚举。
    PROVIDER_REPORTED_NORMALIZED = PROVIDER_REPORTED
    PROVIDER_REPORTED_DELTA = PROVIDER_REPORTED
    SQLITE_TOKEN_INFO = "exact"
    ESTIMATED_PARTIAL = ESTIMATED
    ZERO_FILLED_UNAVAILABLE = "unavailable"
    REPORTED_TOTAL_ONLY = PROVIDER_REPORTED


class TokenTotalSemantics:
    """枚举 total_tokens 的来源语义。"""
    EXCLUSIVE_COMPONENT_SUM = "exclusive_components_sum"
    REPORTED_TOTAL = "reported_total"
    REPORTED_CUMULATIVE_DELTA = "reported_cumulative_delta"
    PROMPT_TOTAL_PLUS_OUTPUT = "prompt_total_plus_output"
    ESTIMATED_COMPONENT_SUM = "estimated_components_sum"
    RECOMPUTED_DUE_TO_INCONSISTENT_RAW_TOTAL = "recomputed_due_to_inconsistent_raw_total"
    REPORTED_TOTAL = "reported_total"


class TokenSourceKind:
    """枚举 token 数据来源。"""
    CLAUDE_CODE_JSONL_USAGE = "claude_code_jsonl_usage"
    CODEX_ROLLOUT_TOKEN_COUNT = "codex_rollout_token_count"
    OPENAI_RESPONSES_USAGE = "openai_responses_usage"
    QODER_SEGMENT_MODEL_RESPONSE_COMPLETED = "qoder_segment_model_response_completed"
    QODER_SQLITE_TOKEN_INFO = "qoder_sqlite_token_info"
    QODER_TURN_FINISHED_FALLBACK = "qoder_turn_finished_fallback"
    QODER_TRANSCRIPT_ESTIMATED = "qoder_transcript_estimated"
    SESSION_TOTAL_ONLY_FALLBACK = "session_total_only_fallback"
    UNKNOWN = "unknown"


class TokenProvider:
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CODEX = "codex"
    QWEN_ANTHROPIC_COMPATIBLE = "qwen-anthropic-compatible"
    QODER = "qoder"
    UNKNOWN = "unknown"


@dataclass
class NormalizedTokenBreakdown:
    """每个 session/LLM call 统一使用的五字段 token breakdown。

    五个 int 字段始终存在（不会是 None/null/NaN）；metadata 字段记录精度和语义。
    """
    fresh_input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    precision: str = TokenPrecision.UNKNOWN
    total_semantics: str = TokenTotalSemantics.EXCLUSIVE_COMPONENT_SUM
    source_kind: str = TokenSourceKind.UNKNOWN
    raw_fields: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "fresh_input_tokens": self.fresh_input_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "precision": self.precision,
            "total_semantics": self.total_semantics,
            "source_kind": self.source_kind,
            "raw_fields": self.raw_fields,
            "notes": self.notes,
        }


# 说明：─── Session / Message / Tool models ──────────────────────────────────────


@dataclass
class SessionSummary:
    """会话索引的当前领域模型，只暴露五字段 token 组件。"""

    agent: str  # 可选值："claude_code" | "codex" | "qoder"
    session_id: str
    title: str
    project_key: str  # 完整归一化路径
    project_name: str  # 路径最后一段
    cwd: str
    started_at: str  # ISO8601 时间字符串
    ended_at: str  # ISO8601 时间字符串
    duration_seconds: float = 0  # 墙钟耗时：首个 event 到最后一个 event
    model_execution_seconds: float = 0  # 合并后的 LLM 响应区间（user msg → assistant msg）
    tool_execution_seconds: float = 0   # 合并后的 tool + subagent 区间（tool_use → tool_result）
    model: str = ""
    git_branch: str = ""
    source: str = ""  # 可选值："cli" | "vscode" | ...
    user_message_count: int = 0
    assistant_message_count: int = 0
    tool_call_count: int = 0
    output_tokens: int = 0
    has_sensitive_data: bool = True

    # 当前统一 token 组件：始终为 int，缺失时填 0。
    fresh_input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0

    token_breakdown: Optional["NormalizedTokenBreakdown"] = None
    failed_tool_count: int = 0
    subagent_instance_count: int = 0
    parse_diagnostics: Optional[dict] = None  # adapter 附加的 ParseDiagnostics.to_dict() payload
    file_path: str = ""  # 已索引源文件路径，详情页 parser 直接复用

    @property
    def session_key(self) -> str:
        return f"{self.agent}:{self.session_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["session_key"] = self.session_key
        return d


@dataclass
class ChatMessage:
    """session 中的一条 chat message（user 或 assistant）。"""

    role: str  # 可选值："user" | "assistant"
    content: str
    timestamp: str  # ISO8601 时间字符串
    model: str = ""
    tool_calls: list[dict] = field(default_factory=list)  # 用于 assistant messages
    usage: Optional[dict] = None  # assistant messages 的 token usage
    content_html: str = ""  # 预渲染的 Markdown HTML
    token_ratio: float = 0  # 该 message 占 session token 的比例
    llm_call_id: str = ""  # provider/Claude message id，对应一个逻辑 LLM call
    llm_status: str = "ok"  # 可选值："ok" | "error"
    request_full: str = ""  # 该 assistant response 前渲染出的 request context
    stop_reason: str = ""  # 说明：e.g. "end_turn", "tool_use", "max_tokens", "stop_sequence"
    content_parts: list["ContentPart"] = field(default_factory=list)  # 类型化 content parts
    content_blocks: list[dict] = field(default_factory=list)  # 按顺序保存的原始 API 层 content blocks


@dataclass
class ToolCall:
    """一条工具调用记录。"""

    name: str
    parameters: dict = field(default_factory=dict)
    result: str = ""
    status: str = "completed"  # 可选值："completed" | "error"
    duration_ms: float = 0
    timestamp: str = ""
    exit_code: Optional[int] = None
    error_message: str = ""
    files_touched: list[str] = field(default_factory=list)
    round_index: int = 0
    tool_use_id: str = ""
    scope: str = "main"  # 可选值："main" | "subagent"
    parent_tool_use_id: str = ""
    parent_tool_name: str = ""
    subagent_id: str = ""
    subagent_summary: dict = field(default_factory=dict)
    llm_call_count: int = 0
    llm_error_count: int = 0
    subagent_tool_call_count: int = 0
    subagent_failed_tool_count: int = 0

    @property
    def is_failed(self) -> bool:
        """工具调用本身失败（运行时错误、API 错误、用户拒绝等）。

        Bash 的非零 exit_code 不等同于工具调用失败；它只记录命令返回码，
        可能是业务语义（例如 rg 无匹配、grep 返回 1、测试失败）。
        """
        return self.status == "error"

    @property
    def has_nonzero_exit(self) -> bool:
        """命令返回了非零 exit code，不代表 tool status 一定失败。"""
        return self.exit_code is not None and self.exit_code != 0


@dataclass
class LLMCall:
    """一次逻辑 LLM API call（main agent 或 subagent）。"""

    id: str                          # msg["id"]，即 llm_call_id
    model: str                       # 说明：e.g. "qwen3.6-plus", "claude-sonnet-4-6"
    scope: str                       # 可选值："main" | "subagent"
    subagent_id: str                 # 可选值："" for main; agent_id for subagent
    round_index: int                 # 从 0 开始的 round index
    parent_id: str                   # 可选值："" for main; parent Agent tool_use_id for subagent
    parent_tool_name: str            # 可选值："" for main; "Agent" for subagent
    timestamp: str                   # ISO8601 时间字符串
    status: str                      # 可选值："ok" | "error"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    prompt_preview: str = ""         # prompt context 前约 200 个字符
    request_preview: str = ""        # logged request 前约 200 个字符
    request_full: str = ""           # 渲染/重建后的 request context，不是原始 HTTP payload
    response_preview: str = ""       # response 前约 200 个字符
    response_full: str = ""          # 完整 response 文本（用于展开）
    # Raw HTTP request payload fields (distinct，来源于 request_full)
    request_payload_raw: str = ""    # 发送给模型的原始 HTTP request JSON（如果已持久化）
    request_payload_message_count: int = 0  # raw payload 中的 message 数量
    request_payload_bytes: int = 0   # raw payload 字节大小
    request_payload_missing_reason: str = ""  # raw payload 不可用原因
    # Raw HTTP response payload fields (distinct，来源于 response_full)
    response_payload_raw: str = ""   # 模型返回的原始 HTTP response JSON（如果已持久化）
    response_payload_missing_reason: str = ""  # raw response 不可用原因
    finish_reason: str = ""          # 说明：e.g. "end_turn", "tool_use", "max_tokens", "stop_sequence"
    tool_calls_raw: str = ""         # 原始 tool calls JSON 结构（如果可用）
    content_blocks: list[dict] = field(default_factory=list)  # 按顺序保存的原始 API 层 content blocks
    tool_calls: list["ToolCall"] = field(default_factory=list)
    tool_call_count: int = 0
    failed_tool_count: int = 0
    token_breakdown_normalized: Optional["NormalizedTokenBreakdown"] = None


@dataclass
class ConversationRound:
    """UI 分组使用的一条 trace row；不是 token 边界。"""

    user_msg: ChatMessage
    assistant_msg: ChatMessage
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_tokens: int = 0
    token_ratio: float = 0  # 占总 session token 的比例
    round_index: int = 0
    llm_call_count: int = 0
    llm_error_count: int = 0
    interactions: list[LLMCall] = field(default_factory=list)
    # 说明：Preview fields — keep separate to avoid duplication in template
    preview_text: str = ""           # 纯文本：user message 或 assistant response，不包含 tool badges
    tool_summary_html: str = ""      # 结构化 tool chips：例如 <span class="preview-tool">Read</span>×2

    @staticmethod
    def _compact_preview_text(text: str, limit: int = 120) -> str:
        """压缩空白并截断为 preview 文本。"""
        import re
        if not text:
            return ""
        compacted = re.sub(r'\s+', ' ', text).strip()
        if len(compacted) > limit:
            return compacted[:limit].rstrip() + '…'
        return compacted

    @staticmethod
    def _format_tool_counts(tools: list[ToolCall]) -> str:
        """返回每种工具的 HTML-safe 计数字段。

        格式：<span class=\"preview-tool\">Bash</span>×1 · <span class=\"preview-tool\">Read</span>×2
        """
        if not tools:
            return ""
        tool_counts: dict[str, int] = {}
        for tc in tools:
            tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1
        parts = [
            f'<span class="preview-tool">{name}</span>×{count}'
            for name, count in tool_counts.items()
        ]
        return ' · '.join(parts)

    def compute_preview(self) -> None:
        """在 interactions/tool_calls 赋值后派生 preview 字段。

        preview 被拆成两个正交部分：
        - preview_text：纯文本摘要（user msg 或 assistant response），不含 tool badges。
        - tool_summary_html：结构化 tool count chips。
        """
        # 使用 round.tool_calls（权威来源），避免同一 round 多个 interactions 时重复计数。
        all_tools = self.tool_calls if self.tool_calls else []
        tool_summary_html = self._format_tool_counts(all_tools) if all_tools else ""

        has_subagent = any(ix.scope == "subagent" for ix in self.interactions)
        subagent_response = ""
        for ix in self.interactions:
            if ix.scope == "subagent" and ix.response_preview and not subagent_response:
                subagent_response = ix.response_preview

        has_user_input = bool(self.user_msg.content)
        has_assistant_content = bool(self.assistant_msg.content)

        if has_subagent:
            if subagent_response:
                preview = self._compact_preview_text(subagent_response, 100)
            else:
                sub_desc = ""
                for ix in self.interactions:
                    if ix.scope == "subagent" and ix.parent_tool_name:
                        sub_desc = ix.parent_tool_name
                        break
                preview = f"Subagent({sub_desc})" if sub_desc else "Subagent"
        elif has_assistant_content:
            preview = self._compact_preview_text(self.assistant_msg.content, 100)
        elif has_user_input:
            preview = self._compact_preview_text(self.user_msg.content, 120)
        else:
            preview = ""

        # Text-only summary，用于 template
        self.preview_text = preview
        self.tool_summary_html = tool_summary_html

    @property
    def input_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("input_tokens", 0)
        return 0

    @property
    def output_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("output_tokens", 0)
        return 0

    @property
    def cached_tokens(self) -> int:
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get(
                "cache_read_input_tokens",
                self.assistant_msg.usage.get("cached_input_tokens", 0),
            )
        return 0

    @property
    def cache_write_tokens(self) -> int:
        """cache_creation_input_tokens：本 turn 写入 cache 的 token。"""
        if self.assistant_msg.usage:
            return self.assistant_msg.usage.get("cache_creation_input_tokens", 0)
        return 0

    def token_breakdown(self) -> dict:
        """返回当前 round 的 token 分类 dict。"""
        if not self.assistant_msg.usage:
            return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
        return {
            "input": self.assistant_msg.usage.get("input_tokens", 0),
            # Codex 使用 cached_input_tokens；Claude/Qoder 使用 cache_read_input_tokens。
            "cache_read": self.assistant_msg.usage.get(
                "cache_read_input_tokens",
                self.assistant_msg.usage.get("cached_input_tokens", 0),
            ),
            "cache_write": self.assistant_msg.usage.get("cache_creation_input_tokens", 0),
            "output": self.assistant_msg.usage.get("output_tokens", 0),
        }


@dataclass
class ProjectStats:
    """项目聚合统计。"""

    project_key: str
    project_name: str
    total_sessions: int = 0
    claude_sessions: int = 0
    codex_sessions: int = 0
    qoder_sessions: int = 0
    first_seen: str = ""
    last_seen: str = ""
    total_fresh_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0  # 缓存读取
    total_cache_write_tokens: int = 0  # 缓存写入
    total_tool_calls: int = 0
    total_user_messages: int = 0
    total_assistant_messages: int = 0
    total_failed_tools: int = 0
