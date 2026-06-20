"""归因核心数据模型。

定义 Evidence、PromptSpan、UsageBreakdown、AttributionResult 等
四层归因架构所需的核心数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ─── ContentRef：内容引用 ────────────────────────────────────────────


@dataclass(frozen=True)
class ContentRef:
    """指向归因内容的安全引用。

    kind: inline | file_slice | session_event | unavailable
    pointer: 具体定位（文件路径 / event ID / byte range）
    preview: 安全截断的预览文本
    can_load_full: 是否支持动态加载全文
    redaction_applied: 是否已脱敏
    """
    kind: str                           # 枚举值：inline / file_slice / session_event / unavailable
    pointer: str | None = None
    preview: str = ""
    can_load_full: bool = False
    redaction_applied: bool = False


# ─── Evidence：取证事实 ──────────────────────────────────────────────


@dataclass(frozen=True)
class Evidence:
    """一条归因输入来源的取证事实。

    scope: 数据来源范围
        - current_session: 当前 session 的事实
        - prior_session: 前序 session 的事实
        - project_repo: 项目仓库文件
        - agent_app: agent 软件内置信息
        - provider_usage: provider/broker usage 数据
        - inferred: 推断信息
    kind: 证据类型（user_message / tool_result / tool_schema / system_prompt / …）
    precision: 精确度（exact / provider_reported / transcript_exact / estimated / heuristic / residual / unavailable）
    confidence: 0.0–1.0 置信度
    """
    evidence_id: str
    scope: str                          # 枚举值：current_session / prior_session / project_repo / agent_app / provider_usage / inferred
    kind: str                           # 枚举值：user_message / tool_result / tool_schema / system_prompt / …
    source_path: str | None = None
    source_event_id: str | None = None
    content_ref: ContentRef | None = None
    text_preview: str = ""
    raw_value: Any = None
    precision: str = "heuristic"
    confidence: float = 0.5
    redaction_state: str = ""


# ─── PromptSpan：API 请求/响应的有序片段 ─────────────────────────────


@dataclass
class PromptSpan:
    """API 请求或响应中的一个有序片段。

    span 按真实 API 顺序排列，携带 token 计数和 cache 分配。
    """
    span_id: str
    order_index: int
    api_family: str
    api_path: str                       # 如 tools[3].input_schema / system[0] / messages[12].content[1]
    semantic_kind: str                  # 枚举值：tool_schema / system_prompt / user_text / tool_result / assistant_text / tool_use / …
    evidence_ids: list[str] = field(default_factory=list)
    content_ref: ContentRef | None = None
    text_preview: str = ""
    raw_json_preview: str | None = None
    token_estimate: int = 0
    token_count_method: str = "heuristic"
    precision: str = "heuristic"
    confidence: float = 0.5
    contributes_to_input: bool = True
    contributes_to_output: bool = False
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    fresh_tokens: int = 0


# ─── UsageBreakdown：用量分解 ────────────────────────────────────────


@dataclass(frozen=True)
class UsageBreakdown:
    """Provider/broker 报告的用量分解。

    所有字段带 precision/source 语义，由 API Family parser 填充。
    """
    total_input: int | None = None
    fresh_input: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    output: int | None = None
    hidden_reasoning: int | None = None

    # 元数据
    usage_source: str = "unknown"       # 枚举值：provider_reported / local_reconstruction / unavailable
    precision: str = "unavailable"
    note: str = ""


# ─── AttributionResult：归因结果 ─────────────────────────────────────


@dataclass
class AttributionResult:
    """单次 LLM call 的完整归因结果。

    同时包含 request 和 response 归因，供 service 层使用。
    """
    request_spans: list[PromptSpan] = field(default_factory=list)
    response_spans: list[PromptSpan] = field(default_factory=list)
    request_buckets: list[dict] = field(default_factory=list)
    response_buckets: list[dict] = field(default_factory=list)
    usage_breakdown: UsageBreakdown | None = None
    evidence_map: dict[str, Evidence] = field(default_factory=dict)
    invariants: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── CreditAttribution：Credit 归因 ─────────────────────────────────


@dataclass
class CallCreditSlice:
    """单个 LLM call 的 credit 切片。"""
    call_id: str
    credits: float | None
    precision: str                      # 枚举值：exact / estimated / unavailable
    source: str = ""


@dataclass
class CreditAttribution:
    """Qoder 等使用 credit 作为计费单位的 credit 归因。"""
    total_credits: float | None = None
    precision: str = "unavailable"
    credit_source: str = ""
    by_model_call: list[CallCreditSlice] = field(default_factory=list)
    effective_rates: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
