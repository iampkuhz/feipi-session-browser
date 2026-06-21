"""session_browser.web.presenters.sessions 模块测试..

覆盖范围:
- parse_sessions_query_params:分页、过滤、排序解析
- compute_pagination:正常情况、边界情况、"all" 模式
- build_sessions_context:结构及与模拟数据库层的集成
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from session_browser.web.presenters.sessions import (
    SORT_KEY_MAP,
    VALID_PAGE_SIZES,
    build_sessions_context,
    compute_pagination,
    parse_sessions_query_params,
)

# ─── parse_sessions_query_params ───────────────────────────────────────


class TestParseSessionsQueryParams:
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_defaults_empty_params(self):
        result = parse_sessions_query_params({})
        assert result['page'] == 1
        assert result['page_size'] == 25
        assert result['filter_agent'] is None
        assert result['filter_model'] is None
        assert result['filter_project'] is None
        assert result['filter_q'] is None
        assert result['sort_by'] == 'ended_at'
        assert result['raw_sort'] == ''
        assert result['sort_dir'] == 'desc'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_valid(self):
        result = parse_sessions_query_params({'page': ['5']})
        assert result['page'] == 5

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_zero_clamps_to_one(self):
        result = parse_sessions_query_params({'page': ['0']})
        assert result['page'] == 1

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_negative_clamps_to_one(self):
        result = parse_sessions_query_params({'page': ['-3']})
        assert result['page'] == 1

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_invalid_string(self):
        result = parse_sessions_query_params({'page': ['abc']})
        assert result['page'] == 1

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_valid(self):
        for size in VALID_PAGE_SIZES:
            result = parse_sessions_query_params({'page_size': [str(size)]})
            assert result['page_size'] == size

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_all(self):
        result = parse_sessions_query_params({'page_size': ['all']})
        assert result['page_size'] == 25

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_ALL_uppercase(self):
        result = parse_sessions_query_params({'page_size': ['ALL']})
        assert result['page_size'] == 25

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_invalid_defaults_to_25(self):
        result = parse_sessions_query_params({'page_size': ['99']})
        assert result['page_size'] == 25

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_non_numeric_defaults_to_25(self):
        result = parse_sessions_query_params({'page_size': ['xyz']})
        assert result['page_size'] == 25

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_filters_parsed(self):
        params = parse_sessions_query_params(
            {
                'agent': ['claude-code'],
                'model': ['sonnet-4'],
                'project': ['my-project'],
                'q': ['search term'],
            }
        )
        assert params['filter_agent'] == 'claude-code'
        assert params['filter_model'] == 'sonnet-4'
        assert params['filter_project'] == 'my-project'
        assert params['filter_q'] == 'search term'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_filters_whitespace_empty_become_none(self):
        params = parse_sessions_query_params(
            {
                'agent': ['  '],
                'model': [''],
            }
        )
        assert params['filter_agent'] is None
        assert params['filter_model'] is None

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_sort_by_valid(self):
        for key, db_col in SORT_KEY_MAP.items():
            result = parse_sessions_query_params({'sort': [key]})
            assert result['sort_by'] == db_col
            assert result['raw_sort'] == key

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_sort_invalid_defaults_to_ended_at(self):
        result = parse_sessions_query_params({'sort': ['unknown']})
        assert result['sort_by'] == 'ended_at'
        assert result['raw_sort'] == 'unknown'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_sort_dir_asc(self):
        result = parse_sessions_query_params({'dir': ['asc']})
        assert result['sort_dir'] == 'asc'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_sort_dir_desc(self):
        result = parse_sessions_query_params({'dir': ['desc']})
        assert result['sort_dir'] == 'desc'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_sort_dir_invalid_defaults_to_desc(self):
        result = parse_sessions_query_params({'dir': ['random']})
        assert result['sort_dir'] == 'desc'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_sort_case_insensitive(self):
        result = parse_sessions_query_params({'sort': ['DURATION'], 'dir': ['ASC']})
        assert result['sort_by'] == 'duration_seconds'
        assert result['sort_dir'] == 'asc'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_combined_params(self):
        result = parse_sessions_query_params(
            {
                'page': ['3'],
                'page_size': ['100'],
                'agent': ['codex'],
                'sort': ['tokens'],
                'dir': ['asc'],
            }
        )
        assert result['page'] == 3
        assert result['page_size'] == 100
        assert result['filter_agent'] == 'codex'
        assert result['sort_by'] == 'total_tokens'
        assert result['sort_dir'] == 'asc'


# ─── compute_pagination ────────────────────────────────────────────────


class TestComputePagination:
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_empty_list(self):
        result = compute_pagination(0, 1, 20)
        assert result['limit'] == 20
        assert result['offset'] == 0
        assert result['total_pages'] == 1
        assert result['page_start'] == 0
        assert result['page_end'] == 0
        assert result['has_prev'] is False
        assert result['has_next'] is False
        assert result['page'] == 1

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_single_page(self):
        result = compute_pagination(15, 1, 20)
        assert result['total_pages'] == 1
        assert result['limit'] == 20
        assert result['offset'] == 0
        assert result['page_start'] == 1
        assert result['page_end'] == 15
        assert result['has_next'] is False
        assert result['has_prev'] is False

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_multi_page_first_page(self):
        result = compute_pagination(100, 1, 20)
        assert result['total_pages'] == 5
        assert result['offset'] == 0
        assert result['limit'] == 20
        assert result['page_start'] == 1
        assert result['page_end'] == 20
        assert result['has_prev'] is False
        assert result['has_next'] is True

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_multi_page_middle_page(self):
        result = compute_pagination(100, 3, 20)
        assert result['page'] == 3
        assert result['offset'] == 40
        assert result['page_start'] == 41
        assert result['page_end'] == 60
        assert result['has_prev'] is True
        assert result['has_next'] is True

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_multi_page_last_page(self):
        result = compute_pagination(100, 5, 20)
        assert result['offset'] == 80
        assert result['page_start'] == 81
        assert result['page_end'] == 100
        assert result['has_next'] is False
        assert result['has_prev'] is True

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_beyond_total_clamped(self):
        result = compute_pagination(50, 10, 20)
        # total_pages = 3,page=10 → 截断到 3
        assert result['page'] == 3
        assert result['offset'] == 40

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_exactly_total_not_clamped(self):
        result = compute_pagination(40, 2, 20)
        assert result['total_pages'] == 2
        assert result['page'] == 2
        assert result['offset'] == 20

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_all(self):
        result = compute_pagination(75, 1, 'all')
        assert result['limit'] == 75
        assert result['offset'] == 0
        assert result['total_pages'] == 1
        assert result['effective_page_size'] == 75
        assert result['page_start'] == 1
        assert result['page_end'] == 75
        assert result['has_next'] is False
        assert result['has_prev'] is False

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_all_empty(self):
        result = compute_pagination(0, 1, 'all')
        assert result['limit'] == 2000
        assert result['offset'] == 0
        assert result['total_pages'] == 1
        assert result['effective_page_size'] == 0

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_size_all_has_next_false(self):
        result = compute_pagination(500, 1, 'all')
        assert result['has_next'] is False

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_effective_page_size_numeric(self):
        result = compute_pagination(50, 1, 20)
        assert result['effective_page_size'] == 20

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_offset_calculation(self):
        for pg, ps, expected_offset in [(1, 20, 0), (2, 20, 20), (5, 100, 400)]:
            result = compute_pagination(1000, pg, ps)
            assert result['offset'] == expected_offset, f'page={pg}, size={ps}'

    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_page_end_capped_at_total(self):
        # 最后一个不完整的页
        result = compute_pagination(55, 3, 20)
        assert result['total_pages'] == 3
        assert result['page_end'] == 55


# ─── build_sessions_context ────────────────────────────────────────────


class TestBuildSessionsContext:
    @staticmethod
    def _make_mock_conn():
        """创建模拟 sqlite3.Connection(带 row factory).."""
        conn = MagicMock()

        # 模拟 count_sessions 返回 0(后续会被覆盖)
        # 模拟 cursor/execute 用于过滤器下拉列表
        mock_models_cursor = MagicMock()
        mock_models_cursor.fetchall.return_value = []
        mock_projects_cursor = MagicMock()
        mock_projects_cursor.fetchall.return_value = []

        def mock_execute(sql, *args):
            if 'DISTINCT model' in sql:
                return mock_models_cursor
            if 'DISTINCT project_key' in sql:
                return mock_projects_cursor
            return MagicMock()

        conn.execute.side_effect = mock_execute
        return conn

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_structure_empty(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 0
        mock_fetch_vm.return_value = {
            'sessions_enriched': [],
            'total_count': 0,
            'sessions_aggregate': {},
            'model_list': [],
            'project_list': [],
        }

        ctx = build_sessions_context({}, conn)

        assert 'sessions' in ctx
        assert 'total_count' in ctx
        assert 'page' in ctx
        assert 'current_page' in ctx
        assert 'page_size' in ctx
        assert 'total_pages' in ctx
        assert 'page_start' in ctx
        assert 'page_end' in ctx
        assert 'has_prev' in ctx
        assert 'has_next' in ctx
        assert 'filter_agent' in ctx
        assert 'filter_model' in ctx
        assert 'filter_project' in ctx
        assert 'filter_q' in ctx
        assert 'sort_by' in ctx
        assert 'sort_dir' in ctx
        assert 'model_list' in ctx
        assert 'project_list' in ctx
        assert 'sessions_aggregate' in ctx

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_values_defaults(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 0
        mock_fetch_vm.return_value = {
            'sessions_enriched': [],
            'total_count': 0,
            'sessions_aggregate': {},
            'model_list': [],
            'project_list': [],
        }

        ctx = build_sessions_context({}, conn)

        assert ctx['total_count'] == 0
        assert ctx['page'] == 1
        assert ctx['current_page'] == 1
        assert ctx['page_size'] == 25
        assert ctx['total_pages'] == 1
        assert ctx['page_start'] == 0
        assert ctx['page_end'] == 0
        assert ctx['has_prev'] is False
        assert ctx['has_next'] is False
        assert ctx['filter_agent'] == ''
        assert ctx['filter_model'] == ''
        assert ctx['filter_project'] == ''
        assert ctx['filter_q'] == ''
        assert ctx['sort_by'] == 'ended-at'
        assert ctx['sort_dir'] == 'desc'

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_with_pagination(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 100
        mock_fetch_vm.return_value = {
            'sessions_enriched': [MagicMock()],
            'total_count': 100,
            'sessions_aggregate': {'avg_tokens': 5000},
            'model_list': ['sonnet-4'],
            'project_list': ['proj-a'],
        }

        ctx = build_sessions_context({'page': ['2'], 'page_size': ['25']}, conn)

        assert ctx['page'] == 2
        assert ctx['current_page'] == 2
        assert ctx['total_count'] == 100
        assert ctx['total_pages'] == 4
        assert ctx['page_start'] == 26
        assert ctx['page_end'] == 50
        assert ctx['has_prev'] is True
        assert ctx['has_next'] is True
        assert ctx['page_size'] == 25

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_with_filters(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 10
        mock_fetch_vm.return_value = {
            'sessions_enriched': [],
            'total_count': 10,
            'sessions_aggregate': {},
            'model_list': ['claude-3'],
            'project_list': [],
        }

        ctx = build_sessions_context(
            {
                'agent': ['claude-code'],
                'model': ['sonnet-4'],
                'q': ['bugfix'],
            },
            conn,
        )

        assert ctx['filter_agent'] == 'claude-code'
        assert ctx['filter_model'] == 'sonnet-4'
        assert ctx['filter_q'] == 'bugfix'

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_sort_mapping(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 0
        mock_fetch_vm.return_value = {
            'sessions_enriched': [],
            'total_count': 0,
            'sessions_aggregate': {},
            'model_list': [],
            'project_list': [],
        }

        # "duration" 排序
        ctx = build_sessions_context({'sort': ['duration'], 'dir': ['asc']}, conn)
        assert ctx['sort_by'] == 'duration'
        assert ctx['sort_dir'] == 'asc'

        # "ended-at" 在模板中映射为 "updated"
        ctx = build_sessions_context({'sort': ['ended-at']}, conn)
        assert ctx['sort_by'] == 'updated'

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_passes_pagination_to_fetch_vm(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 100
        mock_fetch_vm.return_value = {
            'sessions_enriched': [],
            'total_count': 50,
            'sessions_aggregate': {},
            'model_list': [],
            'project_list': [],
        }

        build_sessions_context({'page': ['3'], 'page_size': ['25']}, conn)

        # page=3, size=25 -> offset=50, limit=25
        call_kwargs = mock_fetch_vm.call_args.kwargs
        assert call_kwargs['limit'] == 25
        assert call_kwargs['offset'] == 50

    @patch('session_browser.web.presenters.sessions.count_sessions')
    @patch('session_browser.web.presenters.sessions.fetch_sessions_view_model')
    @pytest.mark.contract_case('DATA-PRESENTER-001')
    def test_context_page_size_all(
        self,
        mock_fetch_vm,
        mock_count,
    ):
        conn = self._make_mock_conn()
        mock_count.return_value = 30
        mock_fetch_vm.return_value = {
            'sessions_enriched': [],
            'total_count': 30,
            'sessions_aggregate': {},
            'model_list': [],
            'project_list': [],
        }

        ctx = build_sessions_context({'page_size': ['all']}, conn)

        assert ctx['page_size'] == 25
        assert ctx['total_pages'] == 2
        assert ctx['page'] == 1
