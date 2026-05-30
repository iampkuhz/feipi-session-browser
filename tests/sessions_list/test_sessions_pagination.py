"""Tests for sessions list pagination — footer."""

from __future__ import annotations

import pytest
import os
import sqlite3
from session_browser.index.indexer import (
    init_schema,
    upsert_session,
    list_sessions,
    count_sessions,
)
from session_browser.domain.models import SessionSummary

_TEMPLATE_PATH = "src/session_browser/web/templates/sessions.html"
_PARTIAL_PATH = "src/session_browser/web/templates/partials/sessions_grid.html"
_UI_PRIMITIVES_PATH = "src/session_browser/web/templates/components/ui_primitives.html"
_SL_COMPONENTS_PATH = "src/session_browser/web/templates/components/sessions_list_components.html"


def _read_sessions_templates():
    """读取 sessions.html、其网格 partial 和组件宏，返回合并内容。"""
    with open(_TEMPLATE_PATH) as f:
        main = f.read()
    with open(_PARTIAL_PATH) as f:
        partial = f.read()
    with open(_UI_PRIMITIVES_PATH) as f:
        ui = f.read()
    with open(_SL_COMPONENTS_PATH) as f:
        sl = f.read()
    return main + "\n" + partial + "\n" + ui + "\n" + sl


def _make_summary(sid: str, title: str = "", agent: str = "claude_code",
                  project: str = "proj-a", model: str = "model-x") -> SessionSummary:
    return SessionSummary(
        agent=agent,
        session_id=sid,
        title=title or f"Session {sid}",
        project_key=project,
        project_name=project,
        cwd="",
        started_at="2026-01-01T00:00:00+00:00",
        ended_at=f"2026-01-{int(sid):02d}T00:00:00+00:00",
        duration_seconds=60,
        model_execution_seconds=30,
        tool_execution_seconds=30,
        model=model,
        git_branch="",
        source="",
        user_message_count=1,
        assistant_message_count=1,
        tool_call_count=1,
        input_tokens=100,
        output_tokens=100,
        cached_input_tokens=0,
        cached_output_tokens=0,
        failed_tool_count=0,
    )


@pytest.fixture
def populated_db(tmp_path):
    """创建包含 55 个 sessions 的 SQLite DB，分布在 3 个 agent 和 3 个 project 下。"""
    db_path = tmp_path / "test_index.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_schema(conn)

    agents = ["claude_code", "qoder", "codex"]
    projects = ["proj-a", "proj-b", "proj-c"]
    models = ["model-x", "model-y"]

    for i in range(1, 56):
        agent = agents[(i - 1) % 3]
        project = projects[(i - 1) % 3]
        model = models[i % 2]
        s = _make_summary(str(i), title=f"Test Session {i:03d}",
                          agent=agent, project=project, model=model)
        upsert_session(conn, s)

    conn.commit()
    yield conn
    conn.close()


# ─── 分页：limit / offset ──────────────────────────────────────────

class TestListSessionsPagination:
    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_default_limit_returns_50(self, populated_db):
        rows = list_sessions(populated_db)
        assert len(rows) == 50

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_limit_20_returns_20(self, populated_db):
        rows = list_sessions(populated_db, limit=20)
        assert len(rows) == 20

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_offset_skips_first_page(self, populated_db):
        first_page = list_sessions(populated_db, limit=20, offset=0)
        second_page = list_sessions(populated_db, limit=20, offset=20)
        first_ids = {r.session_id for r in first_page}
        second_ids = {r.session_id for r in second_page}
        assert first_ids.isdisjoint(second_ids)

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_offset_20_returns_remaining(self, populated_db):
        rows = list_sessions(populated_db, limit=20, offset=20)
        assert len(rows) == 20

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_offset_50_returns_last_5(self, populated_db):
        rows = list_sessions(populated_db, limit=20, offset=50)
        assert len(rows) == 5

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_offset_beyond_data_returns_empty(self, populated_db):
        rows = list_sessions(populated_db, limit=20, offset=100)
        assert len(rows) == 0


# ─── 带过滤条件的计数 ──────────────────────────────────────────────

class TestCountSessionsFilters:
    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_total_count(self, populated_db):
        assert count_sessions(populated_db) == 55

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_count_by_agent(self, populated_db):
        count = count_sessions(populated_db, agent="claude_code")
        assert count > 0

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_count_by_model(self, populated_db):
        count = count_sessions(populated_db, model="model-x")
        assert count > 0

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_count_by_title(self, populated_db):
        count = count_sessions(populated_db, title_like="Test Session 001")
        assert count == 1

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_count_by_title_wildcard(self, populated_db):
        # Sessions 001-009 的标题中都包含 "Session 00"
        count = count_sessions(populated_db, title_like="Session 00")
        assert count == 9  # 001-009

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_count_combined_filters(self, populated_db):
        count = count_sessions(populated_db, agent="claude_code", model="model-x")
        assert count > 0


# ─── 带过滤条件的分页 ─────────────────────────────────────────────

class TestListSessionsWithFilters:
    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_filter_by_agent(self, populated_db):
        rows = list_sessions(populated_db, agent="claude_code", limit=100)
        assert all(r.agent == "claude_code" for r in rows)

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_filter_by_model(self, populated_db):
        rows = list_sessions(populated_db, model="model-y", limit=100)
        assert all(r.model == "model-y" for r in rows)

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_filter_by_title_like(self, populated_db):
        rows = list_sessions(populated_db, title_like="Test Session 00", limit=100)
        assert all("Test Session 00" in r.title for r in rows)


# ─── 模板：footer 控件 ───────────────────────────────────────────

class TestFooterTemplate:
    """验证 sessions.html 包含符合契约的分页。"""

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_pagination_nav(self):
        content = _read_sessions_templates()
        assert 'class="pagination unified-pagination"' in content
        assert 'role="navigation"' in content
        assert 'aria-label="Sessions pagination"' in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_prev_button(self):
        content = _read_sessions_templates()
        assert 'data-action="prev-page"' in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_next_button(self):
        content = _read_sessions_templates()
        assert 'data-action="next-page"' in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_page_input(self):
        content = _read_sessions_templates()
        assert 'data-action="page-input"' in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_page_status(self):
        content = _read_sessions_templates()
        assert 'class="page-status"' in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_no_sorted_by(self):
        """Footer 不得包含 'sorted by' 文本。"""
        content = _read_sessions_templates()
        assert "sorted by" not in content.lower()

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_no_page_size_select_in_footer(self):
        """Footer 不包含页大小选择器。"""
        content = _read_sessions_templates()
        assert "sessions-footer-page-size__select" not in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_no_page_info_text(self):
        """无 'Page X of Y' 静态文本 —— 改用 page-status + page-input。"""
        content = _read_sessions_templates()
        assert 'Page {{ page }} of {{ total_pages }}' not in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_pagination_prev_conditional(self):
        """上一页按钮条件性渲染（第 1 页时隐藏）。"""
        content = _read_sessions_templates()
        assert "current_page > 1" in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_pagination_next_conditional(self):
        """下一页按钮条件性渲染（最后一页时隐藏）。"""
        content = _read_sessions_templates()
        assert "current_page < total_pages" in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_no_button_based_pagination(self):
        """无 name=page 的按钮（旧的基于表单的分页）。"""
        content = _read_sessions_templates()
        assert 'name="page"' not in content or 'value="prev"' not in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_filter_form_has_name_attributes(self):
        content = _read_sessions_templates()
        # 接受单引号和双引号模式（宏使用单引号）
        assert ("name='q'" in content or 'name="q"' in content)
        assert ("name='agent'" in content or 'name="agent"' in content)
        assert ("name='model'" in content or 'name="model"' in content)
        assert ("name='project'" in content or 'name="project"' in content)
        assert 'name="sort"' in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_filter_form_uses_preselected_values(self):
        content = _read_sessions_templates()
        assert "filter_agent" in content
        assert "filter_model" in content
        assert "filter_project" in content
        assert "filter_q" in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_no_client_side_apply_filters(self):
        """旧的客户端 applyFilters 应已移除。"""
        content = _read_sessions_templates()
        assert "function applyFilters()" not in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_no_submit_filters_function(self):
        """submitFilters 已移除，改用基于链接的导航。"""
        content = _read_sessions_templates()
        assert "submitFilters" not in content

    @pytest.mark.contract_case("UI-SESSIONS-012")
    def test_actions_dict_passed(self):
        """模板必须接收 actions 字典用于构建 URL。"""
        content = _read_sessions_templates()
        assert "actions." in content
