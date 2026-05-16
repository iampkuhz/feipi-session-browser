"""Tests for Projects page table restructure."""

from __future__ import annotations

import pytest


class TestTruncatePath:
    """Verify project path display does not show '.' for repo root."""

    def test_repo_root_not_dot(self):
        """A full absolute path should never be truncated to '.'."""
        from session_browser.web.routes import _truncate_path
        result = _truncate_path("/Users/zhehan/Documents/tools/llm/feipi-agent-kit")
        assert result != "."
        assert "feipi-agent-kit" in result

    def test_long_path_truncated(self):
        from session_browser.web.routes import _truncate_path
        path = "/Users/zhehan/some/very/long/path/to/project"
        result = _truncate_path(path)
        # Should preserve beginning and end
        assert result.startswith("/")
        assert "project" in result

    def test_short_path_preserved(self):
        from session_browser.web.routes import _truncate_path
        path = "/tmp/short"
        result = _truncate_path(path)
        assert result == path


class TestProjectsTemplateColumns:
    """Verify the projects.html template has correct columns and no removed ones."""

    def test_no_cache_r_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Cache R" not in content

    def test_no_cache_w_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Cache W" not in content

    def test_no_output_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        # No standalone Output column (may appear in tooltip text, that's OK)
        assert "Output Tokens" not in content

    def test_no_tools_per_round_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Tools/R" not in content

    def test_no_standalone_failed_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert ">Failed</th>" not in content

    def test_has_agents_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Agents" in content

    def test_has_tokens_column(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Tokens" in content


class TestProjectsTemplateSortOptions:
    """Verify sort options no longer include removed columns."""

    def test_no_cache_read_sort(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Cache Read" not in content

    def test_no_cache_write_sort(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Cache Write" not in content

    def test_no_output_tokens_sort(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Output Tokens" not in content

    def test_has_tokens_sort(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Tokens" in content

    def test_has_failed_tools_sort(self):
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "Failed Tools" in content


class TestProjectsTemplatePathDisplay:
    """Verify path display uses truncate_path without relative_to_repo."""

    def test_no_relative_to_repo_for_project_path(self):
        """Project paths should not use relative_to_repo filter."""
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        # The path-text span should use truncate_path directly, not relative_to_repo
        # Check that the path cell doesn't use relative_to_repo
        lines = content.split("\n")
        for line in lines:
            if "project_key" in line and "truncate_path" in line:
                assert "relative_to_repo" not in line

    def test_path_copy_uses_full_project_key(self):
        """Copy button should use the full project_key."""
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "copyProjectPath(this, '{{ p.project_key }}')" in content

    def test_path_tooltip_shows_full_key(self):
        """Tooltip should show the full project_key."""
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert 'data-tooltip="{{ p.project_key }}"' in content


class TestProjectsTemplateTitle:
    """Verify the title doesn't have excessive spacing."""

    def test_title_not_justified_between(self):
        """Title should not use justify-between to separate ( and )."""
        with open("src/session_browser/web/templates/projects.html") as f:
            content = f.read()
        assert "justify-between" not in content
        # Should use a span for the count inline
        assert 'class="card-title' in content
