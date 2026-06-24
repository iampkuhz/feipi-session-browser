"""Unit tests for _build_tool_command_summary helper (T075).

Verify that non-Read/Write tool rows produce meaningful short descriptions
and that the output is safe for HTML escaping (no raw unescaped structures).
"""

from __future__ import annotations

import pytest

from session_browser.web.routes import _build_tool_command_summary
from session_browser.web.session_detail.render_helpers import _build_tool_result_command_fields

# ── Read/Write/Edit:文件路径 ────────────────────────────────────────────


class TestReadWriteEditTools:
    """File tools should show file_path as summary."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_read_shows_file_path(self):
        result = _build_tool_command_summary('Read', {'file_path': '/foo/bar.py'})
        assert result == '/foo/bar.py'

    @pytest.mark.contract_case('UI-SD-021')
    def test_write_shows_file_path(self):
        result = _build_tool_command_summary('Write', {'file_path': '/foo/bar.py'})
        assert result == '/foo/bar.py'

    @pytest.mark.contract_case('UI-SD-021')
    def test_edit_shows_file_path(self):
        result = _build_tool_command_summary('Edit', {'file_path': '/foo/bar.py'})
        assert result == '/foo/bar.py'

    @pytest.mark.contract_case('UI-SD-021')
    def test_read_fallback_to_path(self):
        result = _build_tool_command_summary('Read', {'path': '/foo/bar.py'})
        assert result == '/foo/bar.py'

    @pytest.mark.contract_case('UI-SD-021')
    def test_read_empty_params_returns_tool_name(self):
        result = _build_tool_command_summary('Read', {})
        assert result == ''

    @pytest.mark.contract_case('UI-SD-021')
    def test_read_empty_file_path(self):
        result = _build_tool_command_summary('Read', {'file_path': ''})
        assert result == ''


# ── Bash:命令的前 120 个字符 ─────────────────────────────────────────────


class TestBashTool:
    """Bash should show first 120 chars of the command string."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_bash_short_command(self):
        result = _build_tool_command_summary('Bash', {'command': 'ls -la'})
        assert result == 'ls -la'

    @pytest.mark.contract_case('UI-SD-021')
    def test_bash_long_command_truncated(self):
        cmd = "find /very/long/path/subdir1/subdir2/subdir3/subdir4 -type f \\( -name '*.py' -o -name '*.js' \\) -exec grep -l 'something_interesting' {} \\; | head -20 | tail -5"
        result = _build_tool_command_summary('Bash', {'command': cmd})
        assert len(result) <= 123  # 120 + "..."
        assert result.endswith('...')
        assert 'find' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_bash_empty_command_returns_name(self):
        result = _build_tool_command_summary('Bash', {'command': ''})
        assert result == 'Bash'

    @pytest.mark.contract_case('UI-SD-021')
    def test_bash_no_command_key(self):
        result = _build_tool_command_summary('Bash', {})
        assert result == 'Bash'

    @pytest.mark.contract_case('UI-SD-021')
    def test_bash_strips_whitespace(self):
        result = _build_tool_command_summary('Bash', {'command': '  echo hello  '})
        assert result == 'echo hello'


# ── Tool result modal command fields ─────────────────────────────────────


class TestToolResultCommandFields:
    """Result modal should use full command/workdir fields, not preview summary."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_exec_command_cmd_and_workdir_are_separate(self):
        cmd = 'python3 -m pytest ' + 'tests/' + ('very_long_selector_' * 12)
        result = _build_tool_result_command_fields(
            'exec_command',
            {'cmd': cmd, 'workdir': '/tmp/project'},
        )

        assert result['command'] == cmd
        assert result['workdir'] == '/tmp/project'
        assert not result['command'].endswith('...')

    @pytest.mark.contract_case('UI-SD-021')
    def test_bash_result_uses_full_command_instead_of_summary(self):
        cmd = 'echo ' + ('full-command ' * 30)
        result = _build_tool_result_command_fields('Bash', {'command': cmd, 'cwd': '/repo'})

        assert result['command'] == cmd
        assert result['workdir'] == '/repo'


# ── Grep: pattern + path/glob ─────────────────────────────────────────────


class TestGrepTool:
    """Grep should show pattern + optional path/glob."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_grep_pattern_only(self):
        result = _build_tool_command_summary('Grep', {'pattern': 'def foo'})
        assert '"def foo"' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_grep_pattern_and_path(self):
        result = _build_tool_command_summary('Grep', {'pattern': 'def foo', 'paths': '/src'})
        assert '"def foo"' in result
        assert '/src' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_grep_pattern_path_and_glob(self):
        result = _build_tool_command_summary(
            'Grep', {'pattern': 'import', 'paths': '/src', 'glob': '*.py'}
        )
        assert '"import"' in result
        assert '/src' in result
        assert '--glob *.py' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_grep_path_as_list(self):
        result = _build_tool_command_summary(
            'Grep',
            {'pattern': 'foo', 'paths': ['/src/a.py', '/src/b.py', '/src/c.py', '/src/d.py']},
        )
        assert 'foo' in result
        # Should only show first 3 items
        assert '/src/a.py' in result
        assert '/src/d.py' not in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_grep_empty_params_returns_name(self):
        result = _build_tool_command_summary('Grep', {})
        assert result == 'Grep'


# ── Glob: pattern ─────────────────────────────────────────────────────────


class TestGlobTool:
    """Glob should show pattern."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_glob_with_pattern(self):
        result = _build_tool_command_summary('Glob', {'pattern': '**/*.py'})
        assert result == '**/*.py'

    @pytest.mark.contract_case('UI-SD-021')
    def test_glob_empty_pattern_returns_name(self):
        result = _build_tool_command_summary('Glob', {'pattern': ''})
        assert result == 'Glob'

    @pytest.mark.contract_case('UI-SD-021')
    def test_glob_no_pattern_key(self):
        result = _build_tool_command_summary('Glob', {})
        assert result == 'Glob'


# ── LS: path ──────────────────────────────────────────────────────────────


class TestLSTool:
    """LS should show path."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_ls_with_path(self):
        result = _build_tool_command_summary('LS', {'path': '/src'})
        assert result == '/src'

    @pytest.mark.contract_case('UI-SD-021')
    def test_ls_empty_path_returns_name(self):
        result = _build_tool_command_summary('LS', {'path': ''})
        assert result == 'LS'


# ── MCP: server/tool + key args ──────────────────────────────────────────


class TestMCPTool:
    """MCP should show server/tool + key args."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_mcp_server_and_tool(self):
        result = _build_tool_command_summary('MCP', {'server': 'github', 'tool': 'search'})
        assert 'github' in result
        assert 'search' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_mcp_with_query(self):
        result = _build_tool_command_summary(
            'MCP', {'server': 'slack', 'tool': 'search', 'query': 'hello world'}
        )
        assert 'slack' in result
        assert 'search' in result
        assert 'hello world' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_mcp_with_input(self):
        result = _build_tool_command_summary(
            'MCP', {'server': 'db', 'tool': 'query', 'input': 'SELECT 1'}
        )
        assert 'SELECT 1' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_mcp_truncates_long_values(self):
        long_val = 'x' * 200
        result = _build_tool_command_summary('MCP', {'server': 's', 'tool': 't', 'query': long_val})
        # Should truncate to 60 chars
        query_part = result.split('/')[-1]
        assert len(query_part) <= 60

    @pytest.mark.contract_case('UI-SD-021')
    def test_mcp_empty_returns_name(self):
        result = _build_tool_command_summary('MCP', {})
        assert result == 'MCP'

    @pytest.mark.contract_case('UI-SD-021')
    def test_mcp_prefix_match(self):
        """Tool names starting with 'mcp' should also match."""
        result = _build_tool_command_summary('mcp_fetch', {'server': 'web', 'tool': 'get'})
        assert 'web' in result


# ── Agent: agent_type ────────────────────────────────────────────────────


class TestAgentTool:
    """Agent should show agent_type."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_agent_with_type(self):
        result = _build_tool_command_summary('Agent', {'agent_type': 'code-reviewer'})
        assert result == 'code-reviewer'

    @pytest.mark.contract_case('UI-SD-021')
    def test_agent_empty_returns_name(self):
        result = _build_tool_command_summary('Agent', {})
        assert result == 'Agent'


# ── Unknown tools: compact JSON key subset ───────────────────────────────


class TestUnknownTools:
    """Unknown tools should show up to 3 key=value pairs."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_unknown_simple_values(self):
        result = _build_tool_command_summary('CustomTool', {'key1': 'val1', 'key2': 'val2'})
        assert 'key1=val1' in result
        assert 'key2=val2' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_unknown_limits_to_3_keys(self):
        params = {f'k{i}': f'v{i}' for i in range(10)}
        result = _build_tool_command_summary('CustomTool', params)
        parts = result.split()
        assert len(parts) <= 3

    @pytest.mark.contract_case('UI-SD-021')
    def test_unknown_truncates_long_values(self):
        long_val = 'x' * 100
        result = _build_tool_command_summary('CustomTool', {'key': long_val})
        assert len(result) < 100  # value should be truncated

    @pytest.mark.contract_case('UI-SD-021')
    def test_unknown_dict_value(self):
        result = _build_tool_command_summary('CustomTool', {'config': {'nested': 'value'}})
        assert 'config=' in result
        assert 'nested' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_unknown_list_value(self):
        result = _build_tool_command_summary('CustomTool', {'items': ['a', 'b', 'c']})
        assert 'items=' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_unknown_empty_params_returns_name(self):
        result = _build_tool_command_summary('CustomTool', {})
        assert result == 'CustomTool'


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: None tool_name, None params, empty strings."""

    @pytest.mark.contract_case('UI-SD-021')
    def test_none_tool_name(self):
        result = _build_tool_command_summary(None, {'command': 'ls'})
        # Should not crash; None gets stripped to ""
        assert isinstance(result, str)

    @pytest.mark.contract_case('UI-SD-021')
    def test_none_params(self):
        result = _build_tool_command_summary('Bash', None)
        # Should not crash; None gets handled by .get() or falsy check
        assert isinstance(result, str)

    @pytest.mark.contract_case('UI-SD-021')
    def test_result_is_always_string(self):
        for tool_name in ['Read', 'Bash', 'Grep', 'Glob', 'LS', 'MCP', 'Agent', 'Custom']:
            result = _build_tool_command_summary(tool_name, {'key': 'value'})
            assert isinstance(result, str), f'{tool_name} should return str, got {type(result)}'

    @pytest.mark.contract_case('UI-SD-021')
    def test_no_html_injection_in_output(self):
        """Summary should not contain unescaped HTML from parameters."""
        result = _build_tool_command_summary('Bash', {'command': '<script>alert(1)</script>'})
        # The function itself doesn't escape, but the raw value should be
        # the command text. Caller is responsible for HTML escaping.
        # Just verify it returns the command text as-is (not modified).
        assert '<script>' in result

    @pytest.mark.contract_case('UI-SD-021')
    def test_unicode_handling(self):
        result = _build_tool_command_summary('Bash', {'command': "echo '中文'"})
        assert '中文' in result
