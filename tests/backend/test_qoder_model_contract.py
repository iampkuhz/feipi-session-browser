"""Tests for Qoder model extraction contract.

Covers:
a. assistant message.model flows into SessionSummary.model.
b. cache fixture (no model) does not fabricate a model.
"""

from __future__ import annotations

from session_browser.sources.qoder import (
    _assistant_records,
    _build_summary_from_events,
    _extract_qoder_model,
)


def _make_event(typ: str, message: dict, **extra) -> dict:
    """Helper to build a minimal Qoder event dict."""
    ev = {"type": typ, "message": message, "timestamp": "2025-01-01T00:00:00Z"}
    ev.update(extra)
    return ev


def _assistant_event(model: str = "", text: str = "", msg_id: str = "msg-1", **extra) -> dict:
    """Build an assistant event with optional model and text."""
    content = []
    if text:
        content.append({"type": "text", "text": text})
    msg = {"id": msg_id, "content": content}
    if model:
        msg["model"] = model
    return _make_event("assistant", msg, **extra)


def _user_event(text: str = "") -> dict:
    """Build a user event."""
    return _make_event("user", {"content": text})


class TestQoderModelContract:
    def test_model_from_assistant_message(self):
        """assistant message.model should flow into SessionSummary.model."""
        events = [
            _user_event("hello"),
            _assistant_event(model="qwen3.6-plus", text="hi", msg_id="msg-1"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "qwen3.6-plus", (
            f"Expected model 'qwen3.6-plus' but got {summary.model!r}"
        )

    def test_model_from_first_assistant_with_model(self):
        """When multiple assistant messages, model comes from the first one that has it."""
        events = [
            _user_event("hello"),
            _assistant_event(model="", text="thinking", msg_id="msg-0"),
            _assistant_event(model="qwen3.6-plus", text="answer", msg_id="msg-1"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "qwen3.6-plus"

    def test_cache_fixture_no_model(self):
        """Cache fixture (no model in assistant messages) should not fabricate a model."""
        events = [
            _user_event("hello"),
            _assistant_event(text="hi", msg_id="msg-1"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "", (
            f"Expected empty model but got {summary.model!r}"
        )

    def test_assistant_records_preserve_model(self):
        """_assistant_records should preserve model from message."""
        events = [
            _assistant_event(model="qwen3.6-plus", text="response", msg_id="msg-1"),
        ]

        records = _assistant_records(events)
        assert len(records) == 1
        assert records[0]["model"] == "qwen3.6-plus"

    def test_model_fallback_top_level(self):
        """Priority 2: top-level event.model should be used when message.model is empty."""
        events = [
            _user_event("hello"),
            _assistant_event(model="", text="hi", msg_id="msg-1"),
        ]
        # Inject top-level model into the raw event
        events[1]["model"] = "claude-sonnet-4-20250514"

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "claude-sonnet-4-20250514"

    def test_model_fallback_metadata(self):
        """Priority 3: metadata.model should be used when message.model and top-level are empty."""
        events = [
            _user_event("hello"),
            _assistant_event(model="", text="hi", msg_id="msg-1"),
        ]
        # Inject metadata.model into the raw event
        events[1]["metadata"] = {"model": "claude-opus-4-20250514"}

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "claude-opus-4-20250514"

    def test_model_fallback_content_item(self):
        """Priority 4: model in content item should be used as last resort."""
        events = [
            _user_event("hello"),
            _assistant_event(model="", text="hi", msg_id="msg-1"),
        ]
        # Inject model into a content item
        events[1]["message"]["content"].append({"type": "text", "text": "", "model": "gpt-4.1"})

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "gpt-4.1"

    def test_model_priority_message_wins_over_top_level(self):
        """message.model (Priority 1) should win over top-level model (Priority 2)."""
        events = [
            _user_event("hello"),
            _assistant_event(model="qwen3.6-plus", text="hi", msg_id="msg-1"),
        ]
        events[1]["model"] = "should-not-be-used"

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "qwen3.6-plus"

    def test_extract_qoder_model_returns_none(self):
        """_extract_qoder_model returns None when all fields are empty."""
        record = {
            "model": "",
            "top_level_model": "",
            "metadata_model": "",
            "raw_model": "",
        }
        assert _extract_qoder_model(record) is None

    def test_extract_qoder_model_first_non_empty_wins(self):
        """_extract_qoder_model returns the first non-empty field."""
        record = {
            "model": "",
            "top_level_model": "fallback-model",
            "metadata_model": "metadata-model",
            "raw_model": "raw-model",
        }
        assert _extract_qoder_model(record) == "fallback-model"
