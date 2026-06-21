"""Count tokens with the optional tiktoken library.

The counter is triggered by the tokenization router when local tokenizer precision is
preferred over heuristic estimates. It accepts request or response text and returns a
model-specific count when tiktoken is installed, otherwise ``None`` so callers can fall
back without treating the count as exact provider usage.
"""

from __future__ import annotations

import logging
from functools import cache
from typing import Protocol, cast

logger = logging.getLogger(__name__)

try:
    import tiktoken
except ImportError:
    tiktoken = None


class _TiktokenEncoder(Protocol):
    """Minimal tiktoken encoder protocol used by this module."""

    def encode(self, text: str) -> list[int]:
        """Encode text into token ids.

        Args:
            text: Text to tokenize.

        Returns:
            Token id list produced by the encoder.
        """


@cache
def _get_tiktoken_encoder(model: str) -> _TiktokenEncoder | None:
    """Load and cache a tiktoken encoder for a model.

    Args:
        model: Model name used to select a tiktoken encoding.

    Returns:
        Encoder object when tiktoken is installed and can load the model, otherwise
        ``None``.
    """
    if tiktoken is None:
        logger.debug('tiktoken is not installed; using heuristic counter')
        return None

    try:
        return cast('_TiktokenEncoder', tiktoken.encoding_for_model(model))
    except Exception as exc:
        logger.debug('tiktoken load failed: %s', exc)
        return None


def count_tokens_tiktoken(text: str, model: str = 'gpt-4o') -> int | None:
    """Count text tokens with tiktoken.

    Args:
        text: Request, response, or attribution bucket text to count.
        model: Model name used to select the tiktoken encoding.

    Returns:
        Exact local tokenizer count when available, ``0`` for empty text, or ``None``
        when tiktoken cannot be loaded or cannot encode the text.
    """
    if not text:
        return 0

    encoder = _get_tiktoken_encoder(model)
    if encoder is None:
        return None

    try:
        return len(encoder.encode(text))
    except Exception as exc:
        logger.debug('tiktoken count failed: %s', exc)
        return None
