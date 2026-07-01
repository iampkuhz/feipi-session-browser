"""Sessions List Java/Pebble resource contract tests.

These checks intentionally validate the Java web resources that are rendered by
Playwright.  They no longer assert Python/Jinja macro strings from the old
runtime.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SESSIONS_PATH = ROOT / 'java/web/src/main/resources/templates/sessions.html'
BASE_PATH = ROOT / 'java/web/src/main/resources/templates/base.html'
SESSIONS_CSS_PATH = ROOT / 'java/web/src/main/resources/static/css/sessions-list.css'
SESSIONS_JS_PATH = ROOT / 'java/web/src/main/resources/static/js/sessions-list.js'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _sessions() -> str:
    return _read(SESSIONS_PATH)


class TestSessionsTemplate:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_template_file_exists(self):
        assert SESSIONS_PATH.is_file(), f'{SESSIONS_PATH} must exist'

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_extends_base_and_sets_active_page(self):
        content = _sessions()
        assert '{% extends "base.html" %}' in content
        assert "active_page = 'sessions'" in content
        assert 'hide_sidebar_extra = true' in content

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_no_inline_event_handlers(self):
        content = _sessions()
        assert not re.search(r'\bon(click|change|submit|keydown|keyup)\s*=', content, re.I)


class TestSessionsImports:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_css_and_js_resources_exist_and_are_loaded(self):
        content = _sessions()
        base = _read(BASE_PATH)
        assert SESSIONS_CSS_PATH.is_file()
        assert SESSIONS_JS_PATH.is_file()
        assert 'href="/static/css/sessions-list.css"' in content
        assert 'src="/static/js/sessions-list.js"' in content
        assert 'href="/static/css/ui-primitives.css"' in base
        assert 'src="/static/js/ui_primitives.js"' in base


class TestSessionsPageStructure:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_page_head_and_filter_form(self):
        content = _sessions()
        assert 'class="page-head"' in content
        assert '<h1>Sessions</h1>' in content
        assert 'Browse indexed local agent runs' in content
        assert 'id="session-filter-form"' in content
        assert 'id="session-search"' in content
        for control in ['filter-agent', 'filter-model', 'filter-project', 'filter-status']:
            assert f'id="{control}"' in content
        for label in ['All Agents', 'All Models', 'All Projects']:
            assert label in content
        for cls in [
            'sessions-filter-select--agent',
            'sessions-filter-select--model',
            'sessions-filter-select--project',
            'sessions-filter-select--status',
        ]:
            assert cls in content

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_table_headers_and_sort_contract(self):
        content = _sessions()
        assert 'class="data-table"' in content
        assert 'role="table"' in content
        for header in [
            'Session',
            'Project',
            'Agent',
            'Model',
            'Tokens',
            'Rounds',
            'Tools',
            'Subagents',
            'Duration',
            'Process Time',
            'Failure',
            'Created',
            'Updated',
        ]:
            assert header in content
        for sort_key in [
            'tokens',
            'rounds',
            'tools',
            'subagents',
            'duration',
            'process-time',
            'failure',
            'created',
            'updated',
        ]:
            assert f'data-sort-key="{sort_key}"' in content
        assert 'data-action="sort"' in content
        assert 'c-data-table__sort-icon' in content


class TestSessionsRows:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_row_data_and_links_are_runtime_safe(self):
        content = _sessions()
        assert 'data-action="row"' in content
        for attr in [
            'data-session-key',
            'data-agent',
            'data-model',
            'data-project',
            'data-session-id',
            'data-detail-url',
            'data-total-tokens',
            'data-failed-tools',
        ]:
            assert attr in content
        assert '/sessions/{{ s.agent | urlencode }}/{{ s.sessionId | urlencode }}' in content
        assert 'data-session-link' in content
        assert 'first_chars(12)' in content

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_agent_badges_cover_known_agents(self):
        content = _sessions()
        for badge in ['cc', 'cx', 'qd']:
            assert f"'{badge}'" in content or f' {badge}' in content
        for agent in ['claude_code', 'codex', 'qoder']:
            assert agent in content


class TestSessionsTokenBar:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_tokenbar_uses_actual_token_percentages(self):
        content = _sessions()
        assert 'class="token-total__value"' in content
        assert 'class="tokenbar tokenbar-in-cell"' in content
        for seg in ['fresh', 'read', 'write', 'out']:
            assert f'tokenbar-seg {seg}' in content
        for field in [
            'freshInputTokens',
            'cacheReadTokens',
            'cacheWriteTokens',
            'outputTokens',
        ]:
            assert field in content
        assert '* 100.0 / s_total' in content
        assert 'Token Breakdown' in content


class TestSessionsPaginationAndEmptyState:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_pagination_runtime_contract(self):
        content = _sessions()
        assert 'class="pagination unified-pagination"' in content
        assert 'data-action="prev-page"' in content
        assert 'data-action="next-page"' in content
        assert 'data-action="page-input"' in content
        assert 'data-action="page-size"' in content
        assert 'data-total-pages="{{ total_pages }}"' in content
        assert 'total_count > 0' in content

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_empty_state_distinguishes_filtered_and_true_empty(self):
        content = _sessions()
        assert 'No sessions found' in content
        assert 'No sessions match your current filters.' in content
        assert 'Clear Filters' in content


class TestSessionsBehaviorAssets:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_row_opening_feedback_exists(self):
        js = _read(SESSIONS_JS_PATH)
        css = _read(SESSIONS_CSS_PATH)
        assert 'markRowOpening' in js
        assert 'is-opening' in js
        assert 'is-opening' in css

    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_wide_layout_and_shell_state_ownership(self):
        css = _read(SESSIONS_CSS_PATH)
        assert 'max-width: 1880px' in css
        assert 'body.hide-left' not in css
        assert 'body.focus' not in css


class TestSessionsBreadcrumb:
    @pytest.mark.contract_case('UI-SESSIONS-001', 'UI-SESSIONS-017')
    def test_breadcrumb(self):
        content = _sessions()
        assert 'href="/dashboard"' in content
        assert 'class="current"' in content
