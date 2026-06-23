"""列表视图标题清理测试。

覆盖：
- ``sanitize_list_title`` 工具函数（单元测试）。
- ``list_sessions`` 返回截断后的标题（集成测试）。
- ``get_session`` 返回完整标题（不截断）。
"""

from __future__ import annotations

import sqlite3
import textwrap

import pytest

from session_browser.domain.models import SessionSummary
from session_browser.domain.normalizer import sanitize_list_title
from session_browser.index.indexer import (
    get_session,
    list_sessions,
)
from tests.index._test_db_utils import init_test_schema, insert_test_session

# ─── 单元测试：sanitize_list_title ─────────────────────────────────────────────


class TestSanitizeListTitle:
    """标题清理辅助函数的单元测试。"""

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_empty_string(self):
        assert sanitize_list_title('') == ''

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_none_returns_empty(self):
        assert sanitize_list_title(None) == ''  # type: ignore[arg-type]

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_short_title_unchanged(self):
        assert sanitize_list_title('Fix login bug') == 'Fix login bug'

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_newline_replaced_by_space(self):
        title = 'Line one\nLine two\nLine three'
        result = sanitize_list_title(title)
        assert '\n' not in result
        assert result == 'Line one Line two Line three'

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_whitespace_collapsed(self):
        title = 'hello   world\t\ttest'
        assert sanitize_list_title(title) == 'hello world test'

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_leading_trailing_stripped(self):
        title = '  hello world  '
        assert sanitize_list_title(title) == 'hello world'

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_only_whitespace_returns_empty(self):
        assert sanitize_list_title('   \n\n\t  ') == ''

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_long_title_truncated(self):
        title = 'x' * 200
        result = sanitize_list_title(title)
        assert len(result) == 121  # 120 字符 + "…"
        assert result.endswith('…')

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_truncated_title_does_not_cut_mid_char_at_boundary(self):
        # 边界：120 个字符 —— 去除尾部空白确保省略号前不会出现悬空空格。
        title = 'a' * 120 + ' extra'
        result = sanitize_list_title(title)
        assert len(result) == 121  # 120 + "…"
        assert result.startswith('a' * 120)
        assert result.endswith('…')

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_exact_max_len_no_ellipsis(self):
        title = 'a' * 120
        result = sanitize_list_title(title)
        assert result == title  # 恰好等于最大长度 → 不截断

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_one_over_max_len_gets_ellipsis(self):
        title = 'a' * 121
        result = sanitize_list_title(title)
        assert len(result) == 121  # 120 字符 + "…"
        assert result.endswith('…')

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_custom_max_len(self):
        title = 'a' * 50
        result = sanitize_list_title(title, max_len=30)
        assert len(result) == 31  # 30 + "…"
        assert result.endswith('…')

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_multiline_long_text(self):
        """真实场景：跨多行的多句用户消息。"""
        title = textwrap.dedent("""\
            Create a comprehensive API documentation
            that includes all endpoints, request/response formats,
            error handling, rate limits, authentication methods,
            pagination, filtering, and example code snippets in Python.
            Make sure to cover both REST and GraphQL APIs.
        """)
        result = sanitize_list_title(title)
        assert '\n' not in result
        assert len(result) <= 121  # 120 + "…"
        # 应以开头部分开始
        assert result.startswith('Create a comprehensive API')

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_mixed_whitespace_types(self):
        """混合空格、制表符、换行符、不间断空格。"""
        title = 'hello\t\tworld\n\nfoo\rbar'
        result = sanitize_list_title(title)
        assert result == 'hello world foo bar'


# ─── 集成测试：list_sessions 截断标题，get_session 不截断 ────────────


@pytest.fixture
def tmp_db(tmp_path):
    """创建带有测试 sessions 的临时数据库。"""
    db_path = tmp_path / 'test.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    init_test_schema(conn)

    # 插入具有各种标题的 sessions
    long_title = (
        'This is a very long title that should definitely be truncated because it contains way too many characters for a list view '
        + 'extra padding here'
    )
    sessions = [
        SessionSummary(
            agent='claude_code',
            session_id='sess-1',
            title='Short title',
            project_key='/tmp/p',
            project_name='p',
            cwd='/tmp/p',
            started_at='2026-01-01T00:00:00Z',
            ended_at='2026-01-01T00:01:00Z',
        ),
        SessionSummary(
            agent='claude_code',
            session_id='sess-2',
            title=long_title,
            project_key='/tmp/p',
            project_name='p',
            cwd='/tmp/p',
            started_at='2026-01-01T00:00:00Z',
            ended_at='2026-01-01T00:02:00Z',
        ),
        SessionSummary(
            agent='codex',
            session_id='sess-3',
            title='',
            project_key='/tmp/p',
            project_name='p',
            cwd='/tmp/p',
            started_at='2026-01-01T00:00:00Z',
            ended_at='2026-01-01T00:03:00Z',
        ),
        SessionSummary(
            agent='qoder',
            session_id='sess-4',
            title='Title with\nnewlines\nand\ttabs',
            project_key='/tmp/p',
            project_name='p',
            cwd='/tmp/p',
            started_at='2026-01-01T00:00:00Z',
            ended_at='2026-01-01T00:04:00Z',
        ),
    ]
    for s in sessions:
        insert_test_session(conn, s)
    conn.commit()
    conn.close()
    return db_path


class TestListSessionsTruncatesTitle:
    """集成测试：list_sessions 应返回清理后的标题。"""

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_short_title_unchanged(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        short = next(s for s in sessions if s.session_id == 'sess-1')
        assert short.title == 'Short title'

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_long_title_truncated(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        long_sess = next(s for s in sessions if s.session_id == 'sess-2')
        assert len(long_sess.title) <= 121  # 120 + "…"
        assert long_sess.title.endswith('…')

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_empty_title_stays_empty(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        empty = next(s for s in sessions if s.session_id == 'sess-3')
        assert empty.title == ''

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_newlines_collapsed(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        sessions = list_sessions(conn, limit=50)
        conn.close()
        nl = next(s for s in sessions if s.session_id == 'sess-4')
        assert '\n' not in nl.title
        assert '\t' not in nl.title
        assert ' ' in nl.title  # 换行符已替换为空格


class TestGetSessionFullTitle:
    """get_session 应返回原始完整标题。"""

    @pytest.mark.contract_case('UI-SESSIONS-013')
    def test_long_title_not_truncated(self, tmp_db):
        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        session = get_session(conn, 'claude_code:sess-2')
        conn.close()
        assert session is not None
        assert len(session.title) > 120  # 完整标题已保留
