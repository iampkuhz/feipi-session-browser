"""Codex agent app collectors 测试。"""

from __future__ import annotations

from session_browser.attribution.collectors.agent_app.codex.default_prompt_extractor import (
    extract_default_prompt,
)
from session_browser.attribution.collectors.agent_app.codex.tool_schema_extractor import (
    extract_tool_schemas,
)


class TestCodexDefaultPromptExtractor:
    def test_from_raw_request(self):
        ev = extract_default_prompt(raw_request='You are Codex, a helpful assistant.')
        assert ev is not None
        assert ev.precision == 'extracted'
        assert ev.scope == 'provider_usage'

    def test_from_session_context(self):
        ctx = {'local_instructions': '# Instructions\nBe helpful.'}
        ev = extract_default_prompt(session_context=ctx)
        assert ev is not None
        assert ev.precision == 'extracted'

    def test_heuristic_fallback(self):
        ev = extract_default_prompt()
        assert ev is not None
        assert ev.precision == 'heuristic'
        assert ev.confidence <= 0.5


class TestCodexToolSchemaExtractor:
    def test_returns_multiple_evidences(self):
        results = extract_tool_schemas()
        assert len(results) > 0
        assert all(e.kind == 'tool_schema' for e in results)
        assert all(e.scope == 'agent_app' for e in results)

    def test_not_exact_precision(self):
        """Codex tool schemas 不标 exact。"""
        results = extract_tool_schemas()
        for ev in results:
            assert ev.precision != 'exact'
