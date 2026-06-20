"""Field-first token accounting mapper 测试。"""

from __future__ import annotations

import pytest

from session_browser.attribution.contracts import AttributedValue, ValuePrecision, ValueSource
from session_browser.attribution.mapping.agents.claude_code_token_accounting_mapping import (
    ClaudeCodeTokenAccountingMapper,
)
from session_browser.attribution.mapping.agents.qoder_token_accounting_mapping import (
    QoderTokenAccountingMapper,
)


FIELD_ORDER = [
    "fresh_input_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "output_tokens",
]


def _value(tokens: int) -> AttributedValue:
    return AttributedValue(
        value=tokens,
        unit="tokens",
        precision=ValuePrecision.PROVIDER_REPORTED,
        source=ValueSource.PROVIDER_USAGE,
        fill_strategy="test value",
    )


def _unit(candidate: str, direction: str, text: str, index: int = 1) -> dict:
    return {
        "source_id": f"test:{direction}:{candidate}:{index}",
        "dedupe_key": f"dedupe:{direction}:{candidate}:{index}",
        "origin_path": f"fixture.{candidate}",
        "canonical_source_locator": f"fixture:{candidate}:{index}",
        "unit_type": f"{candidate}_unit",
        "candidate": candidate,
        "direction": direction,
        "event_order": 1,
        "part_index": index,
        "byte_range": [0, len(text.encode("utf-8"))],
        "text": text,
        "label": candidate,
        "preview": text[:120],
    }


@pytest.mark.parametrize("mapper_cls", [ClaudeCodeTokenAccountingMapper, QoderTokenAccountingMapper])
def test_request_accounting_uses_four_stable_fields(mapper_cls):
    """request accounting 只暴露四个稳定 fields。"""
    mapper = mapper_cls()
    payload = mapper.build_request_accounting(
        source_units=[_unit("user_input", "request", "hello")],
        fresh_input=_value(100),
        cache_read=_value(40),
        cache_write=_value(10),
    )

    assert payload["schema"] == "token_accounting_fields.v1"
    assert payload["field_order"] == FIELD_ORDER
    assert set(FIELD_ORDER) <= set(payload)
    assert payload["fresh_input_tokens"]["tokens"] == 100
    assert payload["cache_read_tokens"]["tokens"] == 40
    assert payload["cache_write_tokens"]["tokens"] == 10
    assert payload["output_tokens"]["tokens"] == 0


@pytest.mark.parametrize("mapper_cls", [ClaudeCodeTokenAccountingMapper, QoderTokenAccountingMapper])
def test_cache_fields_do_not_create_provider_cache_candidate(mapper_cls):
    """cache read/write 是 accounting field，不创建 provider_cached_context candidate。"""
    mapper = mapper_cls()
    payload = mapper.build_request_accounting(
        source_units=[_unit("conversation_history", "request", "prior message")],
        fresh_input=_value(100),
        cache_read=_value(900),
        cache_write=_value(50),
    )

    for field in ("cache_read_tokens", "cache_write_tokens"):
        assert payload[field]["candidates"] == []
    candidates = payload["fresh_input_tokens"]["candidates"]
    assert all(item["candidate"] != "provider_cached_context" for item in candidates)


@pytest.mark.parametrize("mapper_cls", [ClaudeCodeTokenAccountingMapper, QoderTokenAccountingMapper])
def test_request_candidates_scale_to_fresh_denominator(mapper_cls):
    """request candidate 估算值超过 fresh 分母时按比例缩放。"""
    mapper = mapper_cls()
    payload = mapper.build_request_accounting(
        source_units=[
            _unit("user_input", "request", "x" * 400, 1),
            _unit("tool_results", "request", "y" * 400, 2),
        ],
        fresh_input=_value(50),
        cache_read=_value(0),
        cache_write=_value(0),
    )

    fresh = payload["fresh_input_tokens"]
    assert fresh["candidate_total_tokens"] <= 50
    assert fresh["unattributed_tokens"] >= 0
    assert {item["candidate"] for item in fresh["candidates"]} == {"user_input", "tool_results"}


@pytest.mark.parametrize("mapper_cls", [ClaudeCodeTokenAccountingMapper, QoderTokenAccountingMapper])
def test_response_candidates_only_enter_output_field(mapper_cls):
    """response source_units 只映射到 output_tokens。"""
    mapper = mapper_cls()
    payload = mapper.build_response_accounting(
        source_units=[
            _unit("assistant_output", "response", "hello", 1),
            _unit("tool_calls", "response", "Read({})", 2),
        ],
        total_output=_value(30),
    )

    assert payload["fresh_input_tokens"]["tokens"] == 0
    assert payload["cache_read_tokens"]["tokens"] == 0
    assert payload["cache_write_tokens"]["tokens"] == 0
    assert payload["output_tokens"]["tokens"] == 30
    assert {item["candidate"] for item in payload["output_tokens"]["candidates"]} == {
        "assistant_output",
        "tool_calls",
    }
