"""session_browser.web.presenters.dashboard 模块测试..

覆盖:
- build_dashboard_view_model:返回结构(所有预期的键)
- 统计数据从模拟 indexer 的数据流
- 空数据场景
- 会话列表截断(limit=2000)和 needs_attention 上限(limit=8)
- agent_scope 和 grain 参数处理
"""

from __future__ import annotations

import sqlite3
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from session_browser.web.presenters import dashboard as dashboard_presenter
from session_browser.web.presenters.dashboard import build_dashboard_view_model

# ─── 辅助函数 ───────────────────────────────────────────────────────────


def _make_mock_session(key: str, index: int) -> dict:
    """创建最小会话字典,含派生指标字段.."""
    return {
        'session_key': key,
        'title': f'Session {index}',
        'agent': 'claude_code',
        'model': 'sonnet-4',
        'project_key': f'proj-{index % 3}',
        'duration_seconds': 60 * index,
        'total_tokens': 1000 * index,
        'total_tool_calls': index,
        'failed_tool_calls': 0,
        'cache_write_ratio': 0.1,
        'tokens_per_second': 100.0,
    }


def _make_session_row(key: str, index: int) -> MagicMock:
    """创建模拟会话行(如 list_sessions 返回),含 to_dict().."""
    row = MagicMock()
    row.to_dict.return_value = _make_mock_session(key, index)
    return row


def _patch_all_indexers():
    """返回 ExitStack,patch 所有外部依赖(含 KPI helpers)..

    用法:
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
    """
    modules = [
        'get_dashboard_stats',
        'list_projects',
        'get_trend_data',
        'get_prompt_activity_trend',
        'get_agent_distribution',
        'get_token_breakdown',
        'compute_aggregate_metrics',
        'list_sessions',
        'compute_derived_metrics',
        'detect_all_anomalies',
        'get_needs_attention',
        'list_agents',
        'list_model_stats',
        # KPI helper functions that query DB directly
        '_compute_kpis',
    ]
    stack = ExitStack()
    patchers = {}
    for name in modules:
        p = patch(f'session_browser.web.presenters.dashboard.{name}')
        patchers[name] = stack.enter_context(p)

    stack.get_patchers = lambda: patchers
    return stack


def _setup_default_mocks(patchers) -> None:
    """设置所有 mock 的默认返回值(空数据场景).."""
    patchers['get_dashboard_stats'].return_value = {
        'total_sessions': 0,
        'claude_sessions': 0,
        'codex_sessions': 0,
        'qoder_sessions': 0,
        'project_count': 0,
        'total_tokens': 0,
        'total_fresh_input_tokens': 0,
        'total_cache_read_tokens': 0,
        'total_cache_write_tokens': 0,
        'total_output_tokens': 0,
        'total_tool_calls': 0,
        'total_failed_tools': 0,
        'total_user_messages': 0,
        'total_assistant_messages': 0,
    }
    patchers['list_projects'].return_value = []
    patchers['get_trend_data'].return_value = []
    patchers['get_prompt_activity_trend'].return_value = []
    patchers['get_agent_distribution'].return_value = []
    patchers['get_token_breakdown'].return_value = MagicMock(
        total_input=0,
        total_output=0,
        total_cached_input=0,
        total_cached_output=0,
        total_tool_calls=0,
        total_failed_tools=0,
    )
    patchers['compute_aggregate_metrics'].return_value = {}
    patchers['list_sessions'].return_value = []
    patchers['compute_derived_metrics'].side_effect = lambda d: d
    patchers['detect_all_anomalies'].return_value = {}
    patchers['get_needs_attention'].return_value = []
    patchers['list_agents'].return_value = []
    patchers['list_model_stats'].return_value = []
    patchers['_compute_kpis'].return_value = []


# ─── 测试 ─────────────────────────────────────────────────────────────


class TestBuildDashboardViewModelStructure:
    """验证返回的字典包含所有预期的顶层键.."""

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_all_keys_present(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            result = build_dashboard_view_model(conn)

        expected_keys = {
            'agent_scope',
            'grain',
            'is_single_agent',
            'stats',
            'kpis',
            'trend',
            'prompt_activity',
            'all_agents_branch',
            'single_agent_branch',
            'needs_attention',
            'cache_health',
            'chart_notes',
            'active_page',
            'agent_sessions_page',
            'agent_sessions_total_pages',
            'agent_sessions_total',
            'agent_sessions_page_size',
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_active_page_is_dashboard(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            result = build_dashboard_view_model(conn)

        assert result['active_page'] == 'dashboard'


class TestStatisticsDataFlow:
    """验证模拟的 indexer 数据正确流入视图模型.."""

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_stats_passed_through(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            stats_data = {
                'total_sessions': 42,
                'claude_sessions': 20,
                'codex_sessions': 15,
                'qoder_sessions': 7,
                'project_count': 5,
                'total_tokens': 999999,
                'total_fresh_input_tokens': 500000,
                'total_cache_read_tokens': 200000,
                'total_cache_write_tokens': 100000,
                'total_output_tokens': 199999,
                'total_tool_calls': 500,
                'total_failed_tools': 10,
                'total_user_messages': 200,
                'total_assistant_messages': 400,
            }
            patchers['get_dashboard_stats'].return_value = stats_data
            patchers['_compute_kpis'].return_value = []
            patchers['list_projects'].return_value = []
            patchers['get_trend_data'].return_value = []
            patchers['get_prompt_activity_trend'].return_value = []
            patchers['get_agent_distribution'].return_value = {}
            patchers['list_sessions'].return_value = []
            patchers['list_model_stats'].return_value = []
            patchers['detect_all_anomalies'].return_value = {}
            patchers['get_needs_attention'].return_value = []
            patchers['list_agents'].return_value = []

            result = build_dashboard_view_model(conn)

        assert result['stats'] == stats_data
        assert result['stats']['total_sessions'] == 42

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_all_agents_preserves_tiny_token_share(self):
        """非零但小于 0.1% 的 agent token share 不应显示成 0.0%.."""
        conn = MagicMock()
        with (
            patch.object(dashboard_presenter, 'list_agents') as list_agents,
            patch.object(dashboard_presenter, 'get_prompt_activity_trend') as prompt_trend,
            patch.object(dashboard_presenter, 'list_model_stats') as model_stats,
        ):
            list_agents.return_value = [
                {
                    'agent': 'claude_code',
                    'session_count': 10,
                    'total_tokens': 1_000_000_000,
                    'total_fresh_input_tokens': 1_000_000_000,
                    'total_cache_read_tokens': 0,
                    'total_cache_write_tokens': 0,
                    'total_output_tokens': 0,
                    'total_tool_calls': 0,
                    'total_failed_tools': 0,
                    'total_assistant_messages': 0,
                    'project_count': 1,
                    'last_active': '',
                },
                {
                    'agent': 'qoder',
                    'session_count': 1,
                    'total_tokens': 100,
                    'total_fresh_input_tokens': 100,
                    'total_cache_read_tokens': 0,
                    'total_cache_write_tokens': 0,
                    'total_output_tokens': 0,
                    'total_tool_calls': 0,
                    'total_failed_tools': 0,
                    'total_assistant_messages': 0,
                    'project_count': 1,
                    'last_active': '',
                },
            ]
            prompt_trend.return_value = []
            model_stats.return_value = []

            result = dashboard_presenter._compute_all_agents_branch(conn)

        qoder = next(row for row in result['agent_rows'] if row['db_agent'] == 'qoder')
        assert qoder['token_share'] == '<0.1%'
        assert qoder['token_share_value'] > 0

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_trend_and_prompt_activity_passed_through(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)
            trend = [{'date': '2024-01-01', 'total_count': 5}]
            prompt = [{'date': '2024-01-01', 'total_prompts': 100}]
            patchers['get_trend_data'].return_value = trend
            patchers['get_prompt_activity_trend'].return_value = prompt

            result = build_dashboard_view_model(conn)

        assert result['trend'] is trend
        assert result['prompt_activity'] is prompt
        # all_agents_branch should be computed (with mock data)
        assert result['all_agents_branch'] is not None


class TestEmptyDataScenario:
    """验证所有 indexer 返回空/零数据时的行为.."""

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_empty_data_returns_valid_structure(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            result = build_dashboard_view_model(conn)

        assert result['stats']['total_sessions'] == 0
        assert result['kpis'] == []
        assert result['trend'] == []
        # all_agents_branch returns structure with default agents even with empty data
        assert result['all_agents_branch'] is not None
        assert 'agent_rows' in result['all_agents_branch']
        assert 'efficiency_rows' in result['all_agents_branch']
        assert result['single_agent_branch'] is None
        assert result['needs_attention'] == []
        assert result['is_single_agent'] is False
        assert result['agent_scope'] == 'all'
        assert result['grain'] == 'day'


class TestCacheHealthSeries:
    """验证 Cache Health 聚合对 Qoder cache 可用性的处理.."""

    def _make_conn(self, rows):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE sessions (
                ended_at TEXT,
                agent TEXT,
                fresh_input_tokens INTEGER,
                cache_read_tokens INTEGER,
                cache_write_tokens INTEGER,
                file_path TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO sessions (
                ended_at, agent, fresh_input_tokens, cache_read_tokens,
                cache_write_tokens, file_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return conn

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_qoder_basic_token_only_cache_health_is_unknown(self, tmp_path):
        raw = tmp_path / 'qoder-basic.jsonl'
        raw.write_text('{"message":{"usage":{"input_tokens":100,"output_tokens":10}}}\n')
        dashboard_presenter._qoder_file_reports_cache_metrics.cache_clear()
        conn = self._make_conn(
            [
                ('', 'qoder', 100, 0, 0, str(raw)),
            ]
        )

        try:
            series = dashboard_presenter._compute_cache_health_series(conn, 10000)
        finally:
            conn.close()

        assert series[0]['qoder_cache_metric_known'] is False
        assert series[0]['qoder_unreported_input_side_tokens'] == 100
        assert series[0]['qoder_fresh_input_tokens'] == 0
        stats = dashboard_presenter._compute_cache_health_stats(series, 'qoder')
        assert stats['latest_ratio'] == 'N/A'

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_qoder_reported_zero_cache_health_stays_zero(self, tmp_path):
        raw = tmp_path / 'qoder-reported-zero.jsonl'
        raw.write_text(
            '{"message":{"usage":{"input_tokens":100,"cache_read_input_tokens":0,"output_tokens":10}}}\n'
        )
        dashboard_presenter._qoder_file_reports_cache_metrics.cache_clear()
        conn = self._make_conn(
            [
                ('', 'qoder', 100, 0, 0, str(raw)),
            ]
        )

        try:
            series = dashboard_presenter._compute_cache_health_series(conn, 10000)
        finally:
            conn.close()

        assert series[0]['qoder_cache_metric_known'] is True
        assert series[0]['qoder_fresh_input_tokens'] == 100
        stats = dashboard_presenter._compute_cache_health_stats(series, 'qoder')
        assert stats['latest_ratio'] == '0.0%'


class TestKpiDescriptions:
    """验证 KPI 行级 tooltip 文案口径.."""

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_primary_and_secondary_kpi_descriptions_are_specific(self):
        kpi = dashboard_presenter._attach_kpi_descriptions(
            {
                'label': 'Failed Tools',
                'value': '3',
                'secondary': [
                    {'label': 'Failure Rate', 'value': '4.1%'},
                    {'label': 'Repeated Failure Sessions', 'value': '2'},
                ],
            }
        )

        assert 'tool result' in kpi['description']
        assert 'badge_description' in kpi
        assert 'failed tool' in kpi['badge_description']
        for row in kpi['secondary']:
            assert row['description']
            assert '定义与计算公式' not in row['description']
            assert '统计口径' not in row['description']

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_all_dashboard_kpi_labels_have_primary_descriptions(self):
        for label in [
            'Projects',
            'Sessions',
            'Total Tokens',
            'Prompt Activity',
            'Cache Read Ratio',
            'Failed Tools',
        ]:
            kpi = dashboard_presenter._attach_kpi_descriptions(
                {
                    'label': label,
                    'value': '1',
                    'secondary': [],
                }
            )
            assert kpi['description']
            assert '统计口径' not in kpi['description']
            assert kpi['badge_description']
            assert '统计口径' not in kpi['badge_description']

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_dashboard_chart_notes_match_scope_and_grain(self):
        notes = dashboard_presenter._build_chart_notes('all', 'day')
        assert notes['sessions'] == '按天新增的 session 总数,按照不同 agent 堆叠.'

        notes = dashboard_presenter._build_chart_notes('claude-code', 'month')
        assert notes['sessions'] == '按月新增的 Claude Code session 数量.'


class TestAgentScopeAndGrain:
    """验证 agent_scope 和 grain 参数处理.."""

    def test_default_scope_is_all(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            result = build_dashboard_view_model(conn)

        assert result['agent_scope'] == 'all'
        assert result['is_single_agent'] is False

    def test_single_agent_scope(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            result = build_dashboard_view_model(conn, agent_scope='claude-code')

        assert result['agent_scope'] == 'claude-code'
        assert result['is_single_agent'] is True

    def test_invalid_scope_defaults_to_all(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            result = build_dashboard_view_model(conn, agent_scope='unknown')

        assert result['agent_scope'] == 'all'

    def test_default_grain_is_day(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            build_dashboard_view_model(conn)

            patchers['get_trend_data'].assert_called_once()
            call_kwargs = patchers['get_trend_data'].call_args.kwargs
            assert call_kwargs.get('days') == 30

    def test_week_grain_uses_140_days(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            build_dashboard_view_model(conn, grain='week')

            patchers['get_trend_data'].assert_called_once()
            call_kwargs = patchers['get_trend_data'].call_args.kwargs
            assert call_kwargs.get('days') == 140

    def test_month_grain_uses_360_days(self):
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            build_dashboard_view_model(conn, grain='month')

            patchers['get_trend_data'].assert_called_once()
            call_kwargs = patchers['get_trend_data'].call_args.kwargs
            assert call_kwargs.get('days') == 360


class TestDataTruncation:
    """验证会话列表 limit 和 needs_attention 上限.."""

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_list_sessions_called_with_limit_2000(self):
        """Presenter 应请求最多 2000 个会话.."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            build_dashboard_view_model(conn)

            # list_sessions should be called for needs_attention computation
            calls = patchers['list_sessions'].call_args_list
            # Find the call without agent filter (for needs_attention)
            needs_attention_call = None
            for call in calls:
                if call.kwargs.get('limit') == 2000:
                    needs_attention_call = call
                    break
            assert needs_attention_call is not None

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_get_needs_attention_called_with_limit_8(self):
        """Presenter 应将 needs_attention 上限设为 8 项.."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            build_dashboard_view_model(conn)

            call_kwargs = patchers['get_needs_attention'].call_args.kwargs
            assert call_kwargs.get('limit') == 8

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_needs_attention_capped_at_8(self):
        """即使 anomalies 含多项,needs_attention 最多返回 8 项.."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)

            capped = [{'session_key': f'sk-{i}'} for i in range(8)]
            patchers['get_needs_attention'].return_value = capped

            result = build_dashboard_view_model(conn)

        assert len(result['needs_attention']) == 8

    @pytest.mark.contract_case('DATA-PRESENTER-002')
    def test_sessions_derived_metrics_applied(self):
        """compute_derived_metrics 应为每个原始会话调用.."""
        conn = MagicMock()
        with _patch_all_indexers() as stack:
            patchers = stack.get_patchers()
            _setup_default_mocks(patchers)
            patchers['get_dashboard_stats'].return_value['total_sessions'] = 3

            raw = [_make_session_row(f'sk-{i}', i) for i in range(3)]
            patchers['list_sessions'].return_value = raw

            build_dashboard_view_model(conn)

            assert patchers['compute_derived_metrics'].call_count == 3
