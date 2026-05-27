"""Tests for session_browser.web.presenters.projects module.

Covers:
- parse_projects_query_params: pagination parsing
- compute_projects_pagination: normal, edge cases, "all" mode
- build_projects_view_model: structure, pagination parameters, page input effect
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from session_browser.web.presenters.projects import (
    VALID_PAGE_SIZES,
    parse_projects_query_params,
    compute_projects_pagination,
    build_projects_view_model,
    build_project_detail_view_model,
)


# ─── parse_projects_query_params ─────────────────────────────────────

class TestParseProjectsQueryParams:

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_defaults_empty_params(self):
        result = parse_projects_query_params({})
        assert result["page"] == 1
        assert result["page_size"] == 20

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_valid(self):
        result = parse_projects_query_params({"page": ["5"]})
        assert result["page"] == 5

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_zero_clamps_to_one(self):
        result = parse_projects_query_params({"page": ["0"]})
        assert result["page"] == 1

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_negative_clamps_to_one(self):
        result = parse_projects_query_params({"page": ["-3"]})
        assert result["page"] == 1

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_invalid_string(self):
        result = parse_projects_query_params({"page": ["abc"]})
        assert result["page"] == 1

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_valid(self):
        for size in VALID_PAGE_SIZES:
            result = parse_projects_query_params({"page_size": [str(size)]})
            assert result["page_size"] == size

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_all(self):
        result = parse_projects_query_params({"page_size": ["all"]})
        assert result["page_size"] == "all"

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_ALL_uppercase(self):
        result = parse_projects_query_params({"page_size": ["ALL"]})
        assert result["page_size"] == "all"

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_invalid_defaults_to_20(self):
        result = parse_projects_query_params({"page_size": ["99"]})
        assert result["page_size"] == 20

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_non_numeric_defaults_to_20(self):
        result = parse_projects_query_params({"page_size": ["xyz"]})
        assert result["page_size"] == 20

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_combined_params(self):
        result = parse_projects_query_params({
            "page": ["3"],
            "page_size": ["50"],
        })
        assert result["page"] == 3
        assert result["page_size"] == 50


# ─── compute_projects_pagination ──────────────────────────────────────

class TestComputeProjectsPagination:

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_empty_list(self):
        result = compute_projects_pagination(0, 1, 20)
        assert result["limit"] == 20
        assert result["offset"] == 0
        assert result["total_pages"] == 1
        assert result["page_start"] == 0
        assert result["page_end"] == 0
        assert result["has_prev"] is False
        assert result["has_next"] is False
        assert result["page"] == 1

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_single_page(self):
        result = compute_projects_pagination(5, 1, 20)
        assert result["total_pages"] == 1
        assert result["limit"] == 20
        assert result["offset"] == 0
        assert result["page_start"] == 1
        assert result["page_end"] == 5
        assert result["has_prev"] is False
        assert result["has_next"] is False

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_multi_page_first_page(self):
        result = compute_projects_pagination(100, 1, 20)
        assert result["total_pages"] == 5
        assert result["offset"] == 0
        assert result["limit"] == 20
        assert result["page_start"] == 1
        assert result["page_end"] == 20
        assert result["has_prev"] is False
        assert result["has_next"] is True

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_multi_page_middle_page(self):
        result = compute_projects_pagination(100, 3, 20)
        assert result["page"] == 3
        assert result["offset"] == 40
        assert result["page_start"] == 41
        assert result["page_end"] == 60
        assert result["has_prev"] is True
        assert result["has_next"] is True

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_multi_page_last_page(self):
        result = compute_projects_pagination(100, 5, 20)
        assert result["offset"] == 80
        assert result["page_start"] == 81
        assert result["page_end"] == 100
        assert result["has_prev"] is True
        assert result["has_next"] is False

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_beyond_total_clamped(self):
        result = compute_projects_pagination(50, 10, 20)
        # total_pages = 3, page 10 -> clamped to 3
        assert result["page"] == 3
        assert result["offset"] == 40

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_exactly_total_not_clamped(self):
        result = compute_projects_pagination(40, 2, 20)
        assert result["total_pages"] == 2
        assert result["page"] == 2
        assert result["offset"] == 20

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_all(self):
        result = compute_projects_pagination(75, 1, "all")
        assert result["limit"] == 75
        assert result["offset"] == 0
        assert result["total_pages"] == 1
        assert result["effective_page_size"] == 75
        assert result["page_start"] == 1
        assert result["page_end"] == 75
        assert result["has_next"] is False
        assert result["has_prev"] is False

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_size_all_empty(self):
        result = compute_projects_pagination(0, 1, "all")
        assert result["limit"] == 2000
        assert result["offset"] == 0
        assert result["total_pages"] == 1
        assert result["effective_page_size"] == 0

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_effective_page_size_numeric(self):
        result = compute_projects_pagination(50, 1, 20)
        assert result["effective_page_size"] == 20

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_offset_calculation(self):
        for pg, ps, expected_offset in [(1, 20, 0), (2, 20, 20), (5, 50, 200)]:
            result = compute_projects_pagination(1000, pg, ps)
            assert result["offset"] == expected_offset, f"page={pg}, size={ps}"

    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_end_capped_at_total(self):
        # Last partial page
        result = compute_projects_pagination(55, 3, 20)
        assert result["total_pages"] == 3
        assert result["page_end"] == 55


# ─── build_projects_view_model ────────────────────────────────────────

class TestBuildProjectsViewModel:

    def _make_mock_conn(self):
        """

Create a mock sqlite3.Connection."""
        return MagicMock()

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_view_model_has_pagination_keys(
        self, mock_list, mock_count,
    ):
        """View model should contain page/page_size/total_pages keys."""
        conn = self._make_mock_conn()
        mock_count.return_value = 0
        mock_list.return_value = []

        result = build_projects_view_model({}, conn)

        assert "page" in result
        assert "current_page" in result
        assert "page_size" in result
        assert "total_pages" in result
        assert "total_count" in result
        assert "page_start" in result
        assert "page_end" in result
        assert "has_prev" in result
        assert "has_next" in result
        assert "projects" in result
        assert "active_page" in result

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_view_model_values_defaults(
        self, mock_list, mock_count,
    ):
        """Default values should be page=1, page_size=20, total_pages=1."""
        conn = self._make_mock_conn()
        mock_count.return_value = 0
        mock_list.return_value = []

        result = build_projects_view_model({}, conn)

        assert result["total_count"] == 0
        assert result["page"] == 1
        assert result["current_page"] == 1
        assert result["page_size"] == 20
        assert result["total_pages"] == 1
        assert result["page_start"] == 0
        assert result["page_end"] == 0
        assert result["has_prev"] is False
        assert result["has_next"] is False

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_view_model_with_pagination(
        self, mock_list, mock_count,
    ):
        """Pagination parameters should flow through to the view model."""
        conn = self._make_mock_conn()
        mock_count.return_value = 100
        mock_list.return_value = [MagicMock()]

        result = build_projects_view_model({"page": ["2"], "page_size": ["20"]}, conn)

        assert result["page"] == 2
        assert result["current_page"] == 2
        assert result["total_count"] == 100
        assert result["total_pages"] == 5
        assert result["page_start"] == 21
        assert result["page_end"] == 40
        assert result["has_prev"] is True
        assert result["has_next"] is True
        assert result["page_size"] == 20

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_view_model_passes_pagination_to_list_projects(
        self, mock_list, mock_count,
    ):
        """list_projects should be called with correct limit/offset."""
        conn = self._make_mock_conn()
        mock_count.return_value = 100
        mock_list.return_value = []

        build_projects_view_model({"page": ["3"], "page_size": ["20"]}, conn)

        # page=3, size=20 -> offset=40, limit=20
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs["limit"] == 20
        assert call_kwargs["offset"] == 40

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_page_input_affects_result_set(
        self, mock_list, mock_count,
    ):
        """Page input parameter should affect the offset passed to list_projects."""
        conn = self._make_mock_conn()
        mock_count.return_value = 200
        mock_list.return_value = []

        build_projects_view_model({"page": ["1"], "page_size": ["20"]}, conn)
        offset_page1 = mock_list.call_args.kwargs["offset"]

        build_projects_view_model({"page": ["5"], "page_size": ["20"]}, conn)
        offset_page5 = mock_list.call_args.kwargs["offset"]

        assert offset_page1 == 0
        assert offset_page5 == 80
        assert offset_page5 > offset_page1

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_view_model_page_size_all(
        self, mock_list, mock_count,
    ):
        """page_size='all' should disable pagination."""
        conn = self._make_mock_conn()
        mock_count.return_value = 30
        mock_list.return_value = []

        result = build_projects_view_model({"page_size": ["all"]}, conn)

        assert result["page_size"] == "all"
        assert result["total_pages"] == 1
        assert result["page"] == 1

    @patch("session_browser.web.presenters.projects.count_projects")
    @patch("session_browser.web.presenters.projects.list_projects")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_view_model_active_page_is_projects(
        self, mock_list, mock_count,
    ):
        """active_page should be 'projects'."""
        conn = self._make_mock_conn()
        mock_count.return_value = 0
        mock_list.return_value = []

        result = build_projects_view_model({}, conn)

        assert result["active_page"] == "projects"


class TestBuildProjectDetailViewModel:

    def _make_mock_conn(self):
        return MagicMock()

    @patch("session_browser.web.presenters.projects.count_sessions")
    @patch("session_browser.web.presenters.projects.get_project_stats")
    @patch("session_browser.web.presenters.projects.list_sessions")
    @pytest.mark.contract_case("DATA-PRESENTER-003", "DATA-PRESENTER-004")
    def test_detail_view_model_has_required_keys(
        self, mock_list_sessions, mock_stats, mock_count,
    ):
        conn = self._make_mock_conn()
        mock_stats.return_value = MagicMock()
        mock_list_sessions.return_value = []
        mock_count.return_value = 0

        result = build_project_detail_view_model(conn, "test-project")

        assert "project" in result
        assert "sessions" in result
        assert "project_key" in result
        assert "active_page" in result
        assert result["project_key"] == "test-project"
        assert result["active_page"] == "projects"
