"""Claude Code agent app collectors 测试。"""

from __future__ import annotations

from session_browser.attribution.collectors.agent_app.claude_code.system_prompt_extractor import (
    extract_system_prompt,
)
from session_browser.attribution.collectors.agent_app.claude_code.tool_registry_extractor import (
    extract_claude_code_tool_registry,
)
from session_browser.attribution.collectors.agent_app.claude_code.tool_schema_normalizer import (
    compute_schema_hash,
    normalize_tool_schema,
)


class TestToolRegistryExtractor:
    def test_returns_multiple_evidences(self):
        results = extract_claude_code_tool_registry()
        assert len(results) > 5  # Claude Code 有多个工具
        assert all(e.kind == 'tool_schema' for e in results)
        assert all(e.scope == 'agent_app' for e in results)


class TestToolSchemaNormalizer:
    def test_normalize_dict(self):
        schema = {'name': 'Bash', 'description': 'Run commands', 'input_schema': {}}
        result = normalize_tool_schema(schema)
        assert 'name' in result
        assert 'description' in result
        assert 'input_schema' in result

    def test_normalize_none(self):
        result = normalize_tool_schema(None)
        assert result == {}

    def test_normalize_string(self):
        result = normalize_tool_schema('{"name": "Test"}')
        assert result['name'] == 'Test'

    def test_stable_hash(self):
        schema = {'name': 'Bash', 'input_schema': {'type': 'object'}}
        h1 = compute_schema_hash(schema)
        h2 = compute_schema_hash(schema)
        assert h1 == h2
        assert len(h1) == 12  # 截断到 12 字符


class TestSystemPromptExtractor:
    def test_from_system_reminder(self):
        ctx = {'system_reminder_content': 'You are a helpful assistant.'}
        ev = extract_system_prompt(ctx)
        assert ev is not None
        assert ev.precision == 'extracted'
        assert ev.scope == 'current_session'

    def test_from_local_instructions(self):
        ctx = {'local_instructions': '# Project Rules\nUse type hints.'}
        ev = extract_system_prompt(ctx)
        assert ev is not None
        assert ev.precision == 'extracted'

    def test_heuristic_fallback(self):
        ev = extract_system_prompt(None)
        assert ev is not None
        assert ev.precision == 'heuristic'
        assert ev.confidence <= 0.5
