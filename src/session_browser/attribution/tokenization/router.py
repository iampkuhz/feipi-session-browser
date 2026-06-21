"""Select and run the token counting strategy for attribution inputs.

The router is triggered when attribution needs a token count for text spans or payload
fragments. It chooses provider-reported totals first, then provider count APIs, then
local tiktoken, then Qoder byte estimation, and finally heuristic character counts.
"""

from __future__ import annotations

import logging
from enum import Enum

from session_browser.attribution.tokenization.heuristic_counter import estimate_tokens_heuristic
from session_browser.attribution.tokenization.qoder_estimator import estimate_qoder_tokens
from session_browser.attribution.tokenization.tiktoken_counter import count_tokens_tiktoken

logger = logging.getLogger(__name__)


class TokenStrategy(Enum):
    """Available token counting strategies and their precision boundaries.

    Attributes:
        PROVIDER_EXACT: Provider-reported total usage; this router only labels fallback spans.
        PROVIDER_API: Provider count-tokens API strategy selected by callers.
        TIKTOKEN: Local tiktoken strategy for model-aware tokenization.
        QODER_ESTIMATOR: Qoder-specific byte-based estimate strategy.
        HEURISTIC: Generic character-based fallback strategy.
    """

    PROVIDER_EXACT = 'provider_exact'
    PROVIDER_API = 'provider_api'
    TIKTOKEN = 'tiktoken'
    QODER_ESTIMATOR = 'qoder_estimator'
    HEURISTIC = 'heuristic'


def select_strategy(
    has_provider_usage: bool = False,
    provider_has_count_api: bool = False,
    tiktoken_available: bool = False,
    is_qoder: bool = False,
) -> TokenStrategy:
    """Select the highest-confidence token counting strategy for one call.

    Args:
        has_provider_usage: Whether provider usage already reports exact totals.
        provider_has_count_api: Whether the provider can count the request payload.
        tiktoken_available: Whether local tiktoken encoding is importable.
        is_qoder: Whether the call came through Qoder-specific estimation rules.

    Returns:
        Token strategy to use for the available payload and precision boundary.
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
    **kwargs: object,
) -> tuple[int, str]:
    """Count tokens for a text span with a selected strategy.

    Args:
        text: Request, response, or attribution bucket text to count.
        strategy: Selected token counting strategy.
        **kwargs: Reserved strategy-specific options from callers.

    Returns:
        Pair of token count and precision label such as ``exact``, ``tiktoken``,
        ``estimated``, or ``heuristic``.
    """
    _ = kwargs
    if not text:
        return 0, 'exact'

    if strategy == TokenStrategy.PROVIDER_EXACT:
        return _heuristic_count(text), 'estimated'

    if strategy == TokenStrategy.TIKTOKEN:
        result = count_tokens_tiktoken(text)
        if result is not None:
            return result, 'tiktoken'
        return _heuristic_count(text), 'heuristic'

    if strategy == TokenStrategy.QODER_ESTIMATOR:
        return estimate_qoder_tokens(text), 'estimated'

    return _heuristic_count(text), 'heuristic'


def _heuristic_count(text: str) -> int:
    """Return the shared heuristic count for router fallback paths.

    Args:
        text: Text span to estimate with the shared heuristic counter.

    Returns:
        Non-negative heuristic token estimate.
    """
    return estimate_tokens_heuristic(text)
