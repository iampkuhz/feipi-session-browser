"""Token counter router：根据可用性和配置选择 token 计数策略。

优先级：
1. provider exact usage summary -> exact total only，不直接给每个 span
2. provider count_tokens API -> optional / disabled unless configured
3. local tokenizer -> tiktoken if installed
4. qoder estimator -> qoder-fast-bytes-v1 或现有策略
5. heuristic counter -> fallback
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class TokenStrategy(Enum):
    """Token 计数策略。"""
    PROVIDER_EXACT = "provider_exact"
    PROVIDER_API = "provider_api"
    TIKTOKEN = "tiktoken"
    QODER_ESTIMATOR = "qoder_estimator"
    HEURISTIC = "heuristic"


def select_strategy(
    has_provider_usage: bool = False,
    provider_has_count_api: bool = False,
    tiktoken_available: bool = False,
    is_qoder: bool = False,
) -> TokenStrategy:
    """选择最佳 token 计数策略。

    Args:
        has_provider_usage: 是否有 provider 报告的 usage
        provider_has_count_api: provider 是否支持 count_tokens API
        tiktoken_available: tiktoken 是否可用
        is_qoder: 是否为 Qoder agent

    Returns:
        选定的策略
    """
    if has_provider_usage:
        return TokenStrategy.PROVIDER_EXACT
    if provider_has_count_api:
        return TokenStrategy.PROVIDER_API
    if tiktoken_available:
        return TokenStrategy.TIKTOKEN
    if is_qoder:
        return TokenStrategy.QODER_ESTIMATOR
    return TokenStrategy.HEURISTIC


def count_tokens(
    text: str,
    strategy: TokenStrategy = TokenStrategy.HEURISTIC,
    **kwargs,
) -> tuple[int, str]:
    """根据策略计数。

    Returns:
        (token_count, precision_label)
        precision_label: "exact" / "tiktoken" / "estimated" / "heuristic"
    """
    if not text:
        return 0, "exact"

    if strategy == TokenStrategy.PROVIDER_EXACT:
        # provider exact 需要外部传入 usage，这里作为 fallback
        return _heuristic_count(text), "estimated"

    elif strategy == TokenStrategy.TIKTOKEN:
        from session_browser.attribution.tokenization.tiktoken_counter import count_tokens_tiktoken
        result = count_tokens_tiktoken(text)
        if result is not None:
            return result, "tiktoken"
        return _heuristic_count(text), "heuristic"

    elif strategy == TokenStrategy.QODER_ESTIMATOR:
        from session_browser.attribution.tokenization.qoder_estimator import estimate_qoder_tokens
        return estimate_qoder_tokens(text), "estimated"

    else:
        return _heuristic_count(text), "heuristic"


def _heuristic_count(text: str) -> int:
    from session_browser.attribution.tokenization.heuristic_counter import estimate_tokens_heuristic
    return estimate_tokens_heuristic(text)
