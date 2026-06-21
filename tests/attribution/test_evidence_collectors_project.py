"""Project Evidence collectors 测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from session_browser.attribution.collectors.project.agents_md_reader import read_agents_md
from session_browser.attribution.collectors.project.claude_md_reader import read_claude_md
from session_browser.attribution.collectors.project.mcp_config_reader import read_mcp_config
from session_browser.attribution.collectors.project.qoder_rules_reader import read_qoder_rules


class TestClaudeMdReader:
    def test_read_existing_claude_md(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / 'CLAUDE.md').write_text('# Test\nThis is a test file.', encoding='utf-8')
            ev = read_claude_md(td)
            assert ev is not None
            assert ev.scope == 'project_repo'
            assert ev.kind == 'project_rules'
            assert 'Test' in ev.text_preview

    def test_missing_claude_md(self):
        with tempfile.TemporaryDirectory() as td:
            ev = read_claude_md(td)
            assert ev is None


class TestAgentsMdReader:
    def test_read_existing_agents_md(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / 'AGENTS.md').write_text('# Agents\nTest agents.', encoding='utf-8')
            ev = read_agents_md(td)
            assert ev is not None
            assert ev.kind == 'project_rules'

    def test_missing_agents_md(self):
        with tempfile.TemporaryDirectory() as td:
            ev = read_agents_md(td)
            assert ev is None


class TestQoderRulesReader:
    def test_read_qoder_rules(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            rules_dir = path / '.qoder' / 'rules'
            rules_dir.mkdir(parents=True)
            (rules_dir / 'test.md').write_text('# Rule\nTest rule.', encoding='utf-8')
            results = read_qoder_rules(td)
            assert len(results) == 1
            assert results[0].kind == 'local_instructions'
            assert 'Rule' in results[0].text_preview

    def test_no_rules_directory(self):
        with tempfile.TemporaryDirectory() as td:
            results = read_qoder_rules(td)
            assert results == []


class TestMcpConfigReader:
    def test_read_mcp_config(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            mcp_data = {
                'mcpServers': {
                    'filesystem': {'command': 'npx', 'args': ['test']},
                },
                'token': 'secret-value',
            }
            import json

            (path / '.mcp.json').write_text(json.dumps(mcp_data), encoding='utf-8')
            ev = read_mcp_config(td)
            assert ev is not None
            assert ev.kind == 'mcp_config'
            # 敏感字段应脱敏
            assert 'secret-value' not in ev.text_preview

    def test_missing_mcp_json(self):
        with tempfile.TemporaryDirectory() as td:
            ev = read_mcp_config(td)
            assert ev is None
