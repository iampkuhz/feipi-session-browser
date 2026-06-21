"""Payload truncation behavior for session detail payload indexes."""

from __future__ import annotations

import time

from session_browser.web.session_detail.payloads import _truncate_payload

UTF8_LIMIT_BYTES = 7
LARGE_TEXT_SIZE = 1_000_000
TRUNCATED_BYTES = 10_000
MAX_LINEAR_SECONDS = 0.25


def test_truncate_payload_respects_utf8_byte_limit() -> None:
    text = 'abc你好def'

    truncated = _truncate_payload(text, UTF8_LIMIT_BYTES)

    assert truncated == 'abc你'
    assert len(truncated.encode('utf-8')) <= UTF8_LIMIT_BYTES


def test_truncate_payload_large_text_is_linear_time() -> None:
    text = 'x' * LARGE_TEXT_SIZE

    started = time.perf_counter()
    truncated = _truncate_payload(text, TRUNCATED_BYTES)
    elapsed = time.perf_counter() - started

    assert truncated == 'x' * TRUNCATED_BYTES
    assert elapsed < MAX_LINEAR_SECONDS
