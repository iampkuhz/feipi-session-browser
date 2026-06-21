"""Usage 提取器：从 session 事件中提取 usage 信息。"""

from __future__ import annotations


def extract_usage_from_events(events: list[dict], call_id: str) -> dict | None:
    """从事件列表中提取特定 LLM call 的 usage 信息。

    支持多种 usage 嵌套格式：
    - top-level ``usage`` / ``usage_metadata``
    - Qoder nested: ``message.usage``
    - 按 ``id`` / ``call_id`` / ``request_id`` / ``message.id`` 匹配

    Args:
        events: session 事件列表
        call_id: 目标 LLM call 的 ID

    Returns:
        usage dict，包含 input_tokens、output_tokens 等字段。
        如果找不到 usage 信息则返回 None。
    """
    for ev in events:
        # 尝试多种 ID 匹配方式
        ev_id = ev.get('id', '') or ev.get('call_id', '') or ev.get('request_id', '')
        # Qoder: 也尝试 message.id 匹配
        msg = ev.get('message', {})
        msg_id = msg.get('id', '') if isinstance(msg, dict) else ''

        if ev_id == call_id or msg_id == call_id:
            # 优先取 top-level usage
            usage = ev.get('usage', ev.get('usage_metadata', None))
            if usage and isinstance(usage, dict):
                return usage
            # 说明：Qoder nested: message.usage
            if isinstance(msg, dict):
                nested_usage = msg.get('usage')
                if nested_usage and isinstance(nested_usage, dict):
                    return nested_usage

    return None


def extract_usage_from_llm_call(llm_call) -> dict | None:
    """从 LLMCall 对象中提取 usage。

    Args:
        llm_call: LLMCall 对象（具有 input_tokens、output_tokens 等属性）

    Returns:
        usage dict
    """
    if not llm_call:
        return None

    usage = {}
    input_tokens = getattr(llm_call, 'input_tokens', 0) or 0
    output_tokens = getattr(llm_call, 'output_tokens', 0) or 0

    if input_tokens > 0:
        usage['input_tokens'] = input_tokens
    if output_tokens > 0:
        usage['output_tokens'] = output_tokens

    # 检查是否有缓存相关字段
    cache_read = getattr(llm_call, 'cache_read_input_tokens', None)
    cache_write = getattr(llm_call, 'cache_creation_input_tokens', None)
    if cache_read is not None:
        usage['cache_read_input_tokens'] = cache_read
    if cache_write is not None:
        usage['cache_creation_input_tokens'] = cache_write

    # 也检查 LLMCall 上的 cache_read_tokens / cache_write_tokens
    # （标准化后的字段名）
    cache_read_std = getattr(llm_call, 'cache_read_tokens', None)
    cache_write_std = getattr(llm_call, 'cache_write_tokens', None)
    if cache_read_std is not None and 'cache_read_input_tokens' not in usage:
        usage['cache_read_input_tokens'] = cache_read_std
    if cache_write_std is not None and 'cache_creation_input_tokens' not in usage:
        usage['cache_creation_input_tokens'] = cache_write_std

    # 检查是否有嵌套 usage 对象
    raw_usage = getattr(llm_call, 'usage', getattr(llm_call, 'usage_metadata', None))
    if raw_usage and isinstance(raw_usage, dict):
        for k, v in raw_usage.items():
            if k not in usage:
                usage[k] = v

    return usage if usage else None
