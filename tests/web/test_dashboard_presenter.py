"""Tests for session_browser.web.presenters.dashboard module.

Covers:
- build_dashboard_view_model: return structure (all expected keys)
- Statistics data flow from mocked indexers
- Empty-data scenario
- Session list truncation (limit=2000) and needs_attention cap (limit=8)
- model_dist.distribution unwrapping
"""
from __future__ import annotations

import pytest
import sqlite3
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from session_browser.web.presenters.dashboard import build_dashboard_view_model


# ─── Helpers ───────────────────────────────────────────────────────────

def _make_mock_session(key: str, index: int) -> dict:
    """Create a minimal session dict with derived metrics fields."""
    return {
        "session_key": key,
        "title": f"Session {index}",
        "agent": "claude_code",
        "model": "sonnet-4",
        "project_key": f"proj-{index % 3}",
        "duration_seconds": 60 * index,
        "total_tokens": 1000 * index,
        "total_tool_calls": index,
        "failed_tool_calls": 0,
        "cache_write_ratio": 0.1,
        "tokens_per_second": 100.0,
    }


def _make_session_row(key: str, index: int) -> MagicMock:
    """Create a mock session row (as returned by list_sessions) with to_dict()."""
    row = MagicMock()
    row.to_dict.return_value = _make_mock_session(key, index)
    return row


def _patch_all_indexers():
    """Return an ExitStack that patches every external dependency.

    Usage:
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
    """
    modules = [
        "get_dashboard_stats",
        "list_projects",
        "get_trend_data",
        "get_prompt_activity_trend",
        "get_model_distribution",
        "get_agent_distribution",
        "get_token_breakdown",
        "compute_aggregate_metrics",
        "list_sessions",
        "compute_derived_metrics",
        "detect_all_anomalies",
        "get_needs_attention",
    ]
    stack = ExitStack()
    patchers = {}
    for name in modules:
        p = patch(f"session_browser.web.presenters.dashboard.{name}")
        patchers[name] = stack.enter_context(p)

    stack.get_patchers = lambda: patchers
    return stack


# ─── Tests ─────────────────────────────────────────────────────────────

class TestBuildDashboardViewModelStructure:
    """Verify the returned dict contains all expected top-level keys."""

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_all_keys_present(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {
                "total_sessions": 10,
                "claude_sessions": 5,
                "codex_sessions": 3,
                "qoder_sessions": 2,
                "project_count": 3,
            }
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            patchers["get_model_distribution"].return_value.distribution = {}
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        expected_keys = {
            "stats", "projects", "trend", "prompt_activity",
            "model_dist", "agent_dist", "tokens", "aggregate",
            "needs_attention", "active_page",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_active_page_is_dashboard(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        assert result["active_page"] == "dashboard"


class TestStatisticsDataFlow:
    """Verify that mocked index data flows through to the view model."""

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_stats_passed_through(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            stats_data = {
                "total_sessions": 42,
                "claude_sessions": 20,
                "codex_sessions": 15,
                "qoder_sessions": 7,
                "project_count": 5,
                "total_tokens": 999999,
            }
            patchers["get_dashboard_stats"].return_value = stats_data
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        assert result["stats"] == stats_data
        assert result["stats"]["total_sessions"] == 42

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_projects_passed_through(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            projects = [MagicMock(project_key="p1"), MagicMock(project_key="p2")]
            patchers["list_projects"].return_value = projects
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        assert result["projects"] is projects

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_trend_and_prompt_activity_passed_through(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            trend = [{"date": "2024-01-01", "total_count": 5}]
            prompt = [{"date": "2024-01-01", "prompt_tokens": 100}]
            patchers["get_trend_data"].return_value = trend
            patchers["get_prompt_activity_trend"].return_value = prompt
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        assert result["trend"] is trend
        assert result["prompt_activity"] is prompt

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_model_distribution_unwrapped(self):
        """model_dist in result should be the .distribution dict, not the object."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {"sonnet-4": 10, "opus-4": 5}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {"claude_code": 15}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        assert result["model_dist"] == {"sonnet-4": 10, "opus-4": 5}
        assert result["agent_dist"] == {"claude_code": 15}


class TestEmptyDataScenario:
    """Verify behavior when all indexers return empty/zero data."""

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_empty_data_returns_valid_structure(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            result = build_dashboard_view_model(conn)

        assert result["stats"]["total_sessions"] == 0
        assert result["projects"] == []
        assert result["trend"] == []
        assert result["model_dist"] == {}
        assert result["agent_dist"] == {}
        assert result["needs_attention"] == []


class TestDataTruncation:
    """Verify session list limit and needs_attention cap."""

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_list_sessions_called_with_limit_2000(self):
        """Presenter should request up to 2000 sessions."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            build_dashboard_view_model(conn)

            patchers["list_sessions"].assert_called_once_with(
                conn, limit=2000, order_by="ended_at"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_get_needs_attention_called_with_limit_8(self):
        """Presenter should cap needs_attention to 8 items."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            build_dashboard_view_model(conn)

            # get_needs_attention is called with (anomalies_map, sessions_lookup, limit=8)
            call_kwargs = patchers["get_needs_attention"].call_args.kwargs
            assert call_kwargs.get("limit") == 8

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_needs_attention_capped_at_8(self):
        """Even if anomalies have many items, needs_attention returns max 8."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}

            # Simulate indexer returning exactly 8 items (the cap)
            capped = [{"session_key": f"sk-{i}"} for i in range(8)]
            patchers["get_needs_attention"].return_value = capped

            result = build_dashboard_view_model(conn)

        assert len(result["needs_attention"]) == 8

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_sessions_derived_metrics_applied(self):
        """compute_derived_metrics should be called for each raw session."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 3}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}

            raw = [_make_session_row(f"sk-{i}", i) for i in range(3)]
            patchers["list_sessions"].return_value = raw
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            build_dashboard_view_model(conn)

            assert patchers["compute_derived_metrics"].call_count == 3


class TestTrendDataParameters:
    """Verify trend functions are called with correct parameters."""

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_trend_data_called_with_365_days(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            build_dashboard_view_model(conn)

            patchers["get_trend_data"].assert_called_once_with(conn, days=365)
            patchers["get_prompt_activity_trend"].assert_called_once_with(conn, days=365)

    @pytest.mark.contract_case("DATA-PRESENTER-002")
    def test_list_projects_called_with_limit_10(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
            patchers["list_projects"].return_value = []
            patchers["get_trend_data"].return_value = []
            patchers["get_prompt_activity_trend"].return_value = []
            mock_model_dist = MagicMock()
            mock_model_dist.distribution = {}
            patchers["get_model_distribution"].return_value = mock_model_dist
            patchers["get_agent_distribution"].return_value = {}
            patchers["get_token_breakdown"].return_value = MagicMock(
                total_input=0, total_output=0,
                total_cached_input=0, total_cached_output=0,
                total_tool_calls=0, total_failed_tools=0,
            )
            patchers["compute_aggregate_metrics"].return_value = {}
            patchers["list_sessions"].return_value = []
            patchers["compute_derived_metrics"].side_effect = lambda d: d
            patchers["detect_all_anomalies"].return_value = {}
            patchers["get_needs_attention"].return_value = []

            build_dashboard_view_model(conn)

            patchers["list_projects"].assert_called_once_with(conn, limit=10)
