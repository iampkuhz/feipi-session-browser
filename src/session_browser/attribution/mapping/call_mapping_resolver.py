"""Call Mapping Resolver：单次 LLM call 的最终 mapping 决策。

将四个概念分开：
- Agent Runtime: claude_code / codex / qoder / unknown
- API Family: anthropic_messages / openai_responses / openai_chat / qoder_broker / estimate_only / …
- Provider/Broker: anthropic / openai / qoder / local_estimator / unknown
- Billing Unit: tokens / credits / dollars / unknown

优先级：
1. raw request/response payload 明确字段
2. usage 字段形状
3. model 字符串
4. agent runtime 默认配置
5. heuristic fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field

from session_browser.attribution.mapping.agent_runtime import resolve_agent_runtime
from session_browser.attribution.mapping.api_family import API_FAMILY_CAPABILITIES
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape


@dataclass
class CallMappingDecision:
    """单次 LLM call 的 mapping 决策结果。

    所有字段都是最终决策，供下游 pipeline 使用。
    """
    agent_runtime: str                  # claude_code / codex / qoder / unknown
    api_family: str                     # anthropic_messages / openai_responses / …
    provider_or_broker: str             # anthropic / openai / qoder / local_estimator / unknown
    underlying_provider: str | None     # 如果 provider 是 broker，这里是真实 provider
    model: str | None
    billing_units: list[str]            # tokens / credits / dollars
    usage_source: str                   # provider_reported / local_reconstruction / unavailable
    confidence: float                   # 0.0–1.0
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_call_mapping(
    *,
    agent: str,
    usage: dict | None = None,
    model: str | None = None,
    raw_request: dict | None = None,
    raw_response: dict | None = None,
) -> CallMappingDecision:
    """为单次 LLM call 解析最终 mapping 决策。

    Args:
        agent: agent 字符串，如 "claude_code", "qoder", "codex"
        usage: provider/broker usage dict
        model: model 字符串
        raw_request: 原始请求 payload
        raw_response: 原始响应 payload

    Returns:
        CallMappingDecision
    """
    agent_runtime = resolve_agent_runtime(agent)
    reasons: list[str] = []
    warnings: list[str] = []
    confidence = 0.5
    usage_source = "unavailable"
    provider_or_broker = "unknown"
    underlying_provider = None
    api_family = "unknown"
    billing_units: list[str] = ["tokens"]

    # ── Step 1: Determine provider/broker from agent runtime ─────
    if agent_runtime == "claude_code":
        provider_or_broker = "anthropic"
        reasons.append("agent is claude_code -> provider anthropic")
    elif agent_runtime == "codex":
        provider_or_broker = "openai"
        reasons.append("agent is codex -> provider openai")
    elif agent_runtime == "qoder":
        provider_or_broker = "qoder"
        billing_units = ["tokens", "credits"]
        reasons.append("agent is qoder -> provider/broker qoder")

    # ── Step 2: Detect API Family from usage shape ───────────────
    usage_shape = detect_usage_shape(usage)

    if agent_runtime == "qoder":
        # Qoder: 固定为 qoder_broker，不根据 usage shape 推断 underlying provider
        api_family = "qoder_broker"
        underlying_provider = None  # Qoder 是 broker，不伪装为 Anthropic/OpenAI
        if usage_shape == "anthropic_messages_like":
            reasons.append("qoder usage has Anthropic-like cache fields (broker-reported)")
            confidence = 0.85
            usage_source = "provider_reported"
        elif usage_shape in ("openai_responses_like", "openai_chat_like"):
            reasons.append("qoder usage has OpenAI-like fields (broker-reported)")
            confidence = 0.85
            usage_source = "provider_reported"
        elif usage_shape == "token_reported_unknown_cache":
            reasons.append("qoder usage has basic tokens but no cache info")
            confidence = 0.6
            usage_source = "provider_reported"
        else:
            # No usage or unrecognized -> estimate_only
            api_family = "estimate_only"
            reasons.append("qoder no usable usage data -> estimate_only")
            confidence = 0.4
            usage_source = "local_reconstruction"
            warnings.append("Qoder 无 usage 数据，使用本地估算")
    elif agent_runtime == "claude_code":
        if usage_shape == "anthropic_messages_like":
            api_family = "anthropic_messages"
            confidence = 0.95
            usage_source = "provider_reported"
            reasons.append("claude_code with Anthropic usage -> anthropic_messages")
        else:
            api_family = "estimate_only"
            confidence = 0.4
            usage_source = "local_reconstruction"
            warnings.append("Claude Code 无预期 Anthropic usage，使用本地估算")
    elif agent_runtime == "codex":
        if usage_shape == "openai_responses_like":
            api_family = "openai_responses"
            confidence = 0.95
            usage_source = "provider_reported"
            reasons.append("codex with OpenAI Responses usage -> openai_responses")
        elif usage_shape == "openai_chat_like":
            api_family = "openai_chat"
            confidence = 0.9
            usage_source = "provider_reported"
            reasons.append("codex with OpenAI Chat usage -> openai_chat")
        elif usage_shape == "token_reported_unknown_cache":
            api_family = "openai_responses"
            confidence = 0.7
            usage_source = "provider_reported"
            reasons.append("codex with basic tokens -> openai_responses (no cache)")
        else:
            api_family = "estimate_only"
            confidence = 0.4
            usage_source = "local_reconstruction"
            warnings.append("Codex 无预期 OpenAI usage，使用本地估算")
    else:
        # unknown agent
        if usage_shape == "anthropic_messages_like":
            api_family = "anthropic_messages_like"
            provider_or_broker = "anthropic"
            confidence = 0.7
            usage_source = "provider_reported"
            reasons.append("unknown agent with Anthropic-like usage")
        elif usage_shape in ("openai_responses_like", "openai_chat_like"):
            api_family = "openai_like"
            provider_or_broker = "openai"
            confidence = 0.7
            usage_source = "provider_reported"
            reasons.append("unknown agent with OpenAI-like usage")
        else:
            api_family = "estimate_only"
            confidence = 0.3
            usage_source = "local_reconstruction"
            reasons.append("unknown agent, no usage -> estimate_only")

    return CallMappingDecision(
        agent_runtime=agent_runtime,
        api_family=api_family,
        provider_or_broker=provider_or_broker,
        underlying_provider=underlying_provider,
        model=model,
        billing_units=billing_units,
        usage_source=usage_source,
        confidence=confidence,
        reasons=reasons,
        warnings=warnings,
    )
