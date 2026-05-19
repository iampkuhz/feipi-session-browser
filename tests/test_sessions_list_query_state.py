"""Tests for build_sessions_url query state helper."""
import pytest
import sys
import os

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from session_browser.web.routes import build_sessions_url, _build_view_actions


class TestBuildSessionsUrl:
    def test_basic_path(self):
        url = build_sessions_url()
        assert url == "/sessions"

    def test_with_current_params(self):
        url = build_sessions_url(current={"agent": "claude_code", "page": "2"})
        assert "agent=claude_code" in url
        assert "page=2" in url

    def test_updates_add_param(self):
        url = build_sessions_url(current={}, updates={"sort": "tokens"})
        assert "sort=tokens" in url

    def test_updates_remove_param(self):
        url = build_sessions_url(current={"agent": "claude_code", "page": "3"}, updates={"agent": None})
        assert "agent" not in url
        assert "page=3" in url

    def test_reset_page(self):
        url = build_sessions_url(current={"page": "5"}, updates={"sort": "tokens"}, reset_page=True)
        assert "page" not in url
        assert "sort=tokens" in url

    def test_empty_values_filtered(self):
        url = build_sessions_url(current={"agent": "", "q": "  "})
        assert "agent" not in url
        assert "q" not in url

    def test_stable_param_order(self):
        url = build_sessions_url(current={"project": "x", "agent": "cc", "sort": "updated"})
        # q should come before agent before project
        q_idx = url.find("q=")
        agent_idx = url.find("agent=")
        project_idx = url.find("project=")
        # agent should appear before project
        assert agent_idx < project_idx

    def test_no_reset_page_when_no_updates(self):
        url = build_sessions_url(current={"page": "2"})
        assert "page=2" in url

    def test_page_not_reset_for_pagination(self):
        url = build_sessions_url(
            current={"agent": "cc", "page": "2"},
            updates={"page": "3"},
        )
        assert "page=3" in url


class TestBuildViewActions:
    def _actions(self, **kw):
        defaults = {
            "filters": {"q": "", "agent": "cc", "project": "x", "model": ""},
            "sort_key": "updated",
            "sort_dir": "desc",
            "page": 2,
            "page_size": 20,
            "has_prev": True,
            "has_next": True,
        }
        defaults.update(kw)
        return _build_view_actions(**defaults)

    def test_sort_urls_all_five(self):
        a = self._actions()
        for key in ["tokens", "rounds", "tools", "duration", "updated"]:
            assert key in a["sort_urls"], f"missing sort url for {key}"
            assert "/sessions?" in a["sort_urls"][key]

    def test_sort_url_resets_page(self):
        a = self._actions()
        url = a["sort_urls"]["tokens"]
        assert "page" not in url

    def test_sort_url_preserves_filters(self):
        a = self._actions()
        url = a["sort_urls"]["tokens"]
        assert "agent=cc" in url
        assert "project=x" in url

    def test_prev_url_preserves_state(self):
        a = self._actions()
        url = a["prev_url"]
        assert "agent=cc" in url
        assert "project=x" in url
        assert "sort=updated" in url
        assert "page=1" in url

    def test_next_url_preserves_state(self):
        a = self._actions()
        url = a["next_url"]
        assert "page=3" in url
        assert "sort=updated" in url

    def test_no_prev_url_on_first_page(self):
        a = self._actions(has_prev=False)
        assert a["prev_url"] == ""

    def test_no_next_url_on_last_page(self):
        a = self._actions(has_next=False)
        assert a["next_url"] == ""

    def test_remove_filter_urls(self):
        a = self._actions(filters={"q": "abc", "agent": "cc", "project": "x", "model": ""})
        assert "q" in a["remove_filter_urls"]
        assert "agent" in a["remove_filter_urls"]
        assert "project" in a["remove_filter_urls"]
        assert "model" not in a["remove_filter_urls"]

    def test_remove_filter_url_removes_param(self):
        a = self._actions(filters={"q": "abc", "agent": "cc", "project": "x", "model": ""})
        url = a["remove_filter_urls"]["project"]
        assert "project" not in url
        assert "agent=cc" in url

    def test_clear_all_url(self):
        a = self._actions(filters={"q": "abc", "agent": "cc", "project": "x", "model": ""})
        url = a["clear_all_url"]
        assert "q" not in url
        assert "agent" not in url
        assert "project" not in url
        assert "sort=updated" in url

    def test_refresh_url(self):
        a = self._actions()
        url = a["refresh_url"]
        assert "agent=cc" in url
        assert "sort=updated" in url
        assert "dir=desc" in url
