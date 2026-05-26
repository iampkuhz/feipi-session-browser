"""Tests for Qoder model extraction contract.

Covers:
a. assistant message.model flows into SessionSummary.model.
b. cache fixture (no model) does not fabricate a model.
"""

from __future__ import annotations

import json
import sqlite3

from session_browser.sources.qoder import (
    _assistant_records,
    _build_qoder_session_model_map,
    _build_summary_from_events,
    _extract_qoder_model,
    _parse_cache_session,
    _resolve_qoder_model_config_name,
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

    def test_custom_model_config_resolves_to_alias(self):
        """custom:model_x should resolve via aicoding.customModels alias."""
        custom_names = {
            "model_123": "Qwen-3.6-Plus",
            "custom:model_123": "Qwen-3.6-Plus",
        }

        assert _resolve_qoder_model_config_name(
            "custom:model_123",
            custom_names=custom_names,
            selector_names={},
            auth_names={},
        ) == "Qwen-3.6-Plus"

    def test_builtin_model_config_resolves_to_dynamic_label(self):
        """Built-in ids such as qmodel should resolve to selector labels."""
        assert _resolve_qoder_model_config_name(
            "qmodel",
            custom_names={},
            selector_names={"qmodel": "Qwen3.6-Plus"},
            auth_names={},
        ) == "Qwen3.6-Plus"

    def test_session_model_map_from_agent_log_custom_model(self, tmp_path):
        """Qoder agent.log session model config should map to custom model alias."""
        app_support = tmp_path / "Qoder"
        global_storage = app_support / "User" / "globalStorage"
        global_storage.mkdir(parents=True)
        conn = sqlite3.connect(global_storage / "state.vscdb")
        conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            (
                "aicoding.customModels",
                json.dumps([{
                    "id": "model_123",
                    "provider": "bailian",
                    "model": "qwen3.6-plus-cp",
                    "alias": "Qwen-3.6-Plus",
                    "hasApiKey": True,
                }]),
            ),
        )
        conn.commit()
        conn.close()

        log_dir = app_support / "logs" / "20260512T221746" / "window1"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.log").write_text(
            "2026-05-12 22:17:51.528 [info] [ModelSelector] "
            "activeModelConfig=custom:model_123, sessionType=assistant, "
            "sessionId=session-abc\n",
            encoding="utf-8",
        )

        assert (
            _build_qoder_session_model_map(app_support)["session-abc"]
            == "Qwen-3.6-Plus"
        )

    def test_session_model_map_adds_unique_short_id_prefix(self, tmp_path):
        """Cache JSONL short ids should resolve from full GUI session UUIDs."""
        app_support = tmp_path / "Qoder"
        user_dir = app_support / "User"
        user_dir.mkdir(parents=True)
        (user_dir / "dynamic-text-cache.json").write_text(
            json.dumps({"zh-cn": {"modelSelector.item.qmodel": "Qwen3.6-Plus"}}),
            encoding="utf-8",
        )
        log_dir = app_support / "logs" / "20260527T000152" / "window1"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.log").write_text(
            "2026-05-27 00:01:57.765 [info] [ModelConfigService] "
            "getCurrentModelConfig: "
            "sessionId=4df638fa-ab30-413d-b155-7fc550f19703, "
            "returning from storage: qmodel\n",
            encoding="utf-8",
        )

        model_map = _build_qoder_session_model_map(app_support)
        assert model_map["4df638fa-ab30-413d-b155-7fc550f19703"] == "Qwen3.6-Plus"
        assert model_map["4df638fa"] == "Qwen3.6-Plus"

    def test_summary_model_falls_back_to_agent_log(self, tmp_path, monkeypatch):
        """SessionSummary.model should use Qoder GUI agent log when JSONL lacks model."""
        app_support = tmp_path / "Qoder"
        user_dir = app_support / "User"
        user_dir.mkdir(parents=True)
        (user_dir / "dynamic-text-cache.json").write_text(
            json.dumps({"zh-cn": {"modelSelector.item.qmodel": "Qwen3.6-Plus"}}),
            encoding="utf-8",
        )
        log_dir = app_support / "logs" / "20260512T221746" / "window1"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.log").write_text(
            "2026-05-12 22:17:51.528 [info] [ModelSelector] "
            "activeModelConfig=qmodel, sessionType=assistant, sessionId=sess-1\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("QODER_APP_SUPPORT_DIR", str(app_support))

        events = [
            _user_event("hello"),
            _assistant_event(model="", text="hi", msg_id="msg-1"),
        ]

        summary = _build_summary_from_events(events, "sess-1", "/tmp")
        assert summary.model == "Qwen3.6-Plus"

    def test_cache_session_model_falls_back_to_agent_log(self, tmp_path, monkeypatch):
        """Cache-format sessions should also get model from Qoder agent logs."""
        app_support = tmp_path / "Qoder"
        user_dir = app_support / "User"
        user_dir.mkdir(parents=True)
        (user_dir / "dynamic-text-cache.json").write_text(
            json.dumps({"zh-cn": {"modelSelector.item.lite": "Lite"}}),
            encoding="utf-8",
        )
        log_dir = app_support / "logs" / "20260512T221746" / "window1"
        log_dir.mkdir(parents=True)
        (log_dir / "agent.log").write_text(
            "2026-05-12 22:17:51.528 [info] [ModelConfigService] "
            "getCurrentModelConfig: sessionId=cache-1, returning from memory: lite\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("QODER_APP_SUPPORT_DIR", str(app_support))

        session_file = tmp_path / "cache-1.jsonl"
        session_file.write_text(
            json.dumps({"role": "user", "message": {"content": "hello"}}) + "\n"
            + json.dumps({
                "role": "assistant",
                "message": {"content": [{"type": "text", "text": "hi"}]},
            })
            + "\n",
            encoding="utf-8",
        )

        summary = _parse_cache_session("project", "cache-1", session_file)
        assert summary.model == "Lite"
