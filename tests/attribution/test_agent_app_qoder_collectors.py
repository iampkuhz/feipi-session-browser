"""Qoder agent app collectors 测试。"""

from __future__ import annotations

from session_browser.attribution.collectors.agent_app.qoder.builtin_tools_catalog import (
    extract_qoder_builtin_tools,
)
from session_browser.attribution.collectors.agent_app.qoder.model_policy_reader import (
    read_model_policy,
)


class TestQoderBuiltinToolsCatalog:
    def test_returns_multiple_evidences(self):
        results = extract_qoder_builtin_tools()
        assert len(results) > 0
        assert all(e.kind == 'tool_schema' for e in results)
        assert all(e.scope == 'agent_app' for e in results)

    def test_not_exact_precision(self):
        """Qoder builtin tools 不标 exact。"""
        results = extract_qoder_builtin_tools()
        for ev in results:
            assert ev.precision != 'exact'


class TestQoderModelPolicyReader:
    def test_read_existing_policy(self, tmp_path):
        import json

        policy_file = tmp_path / 'policy.json'
        policy_file.write_text(json.dumps({'model': 'test', 'max_tokens': 4096}), encoding='utf-8')
        ev = read_model_policy(str(policy_file))
        assert ev is not None
        assert ev.kind == 'model_policy'
        assert ev.precision == 'extracted'

    def test_missing_policy(self):
        ev = read_model_policy('/nonexistent/path.json')
        assert ev is None

    def test_no_path_provided(self):
        ev = read_model_policy(None)
        assert ev is None
