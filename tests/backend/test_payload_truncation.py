"""Payload truncation behavior for session detail payload indexes."""

from __future__ import annotations

import time

from session_browser.web.session_detail.payloads import _truncate_payload


def test_truncate_payload_respects_utf8_byte_limit() -> None:
    text = "abc你好def"

    truncated = _truncate_payload(text, 7)

    assert truncated == "abc你"
    assert len(truncated.encode("utf-8")) <= 7


def test_truncate_payload_large_text_is_linear_time() -> None:
    text = "x" * 1_000_000

    started = time.perf_counter()
    truncated = _truncate_payload(text, 10_000)
    elapsed = time.perf_counter() - started

    assert truncated == "x" * 10_000
    assert elapsed < 0.25
