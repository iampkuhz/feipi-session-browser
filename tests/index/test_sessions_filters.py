"""Session list filter tests.

Validates that `title_like` search is case-insensitive and matches
both title and session_id as substrings (S-13: session id 搜索支持
不区分大小写子串匹配).
"""

import sqlite3
from contextlib import closing

import pytest

from session_browser.domain.models import SessionSummary
from session_browser.index.indexer import (
    count_sessions,
    list_sessions,
)
from tests.index._test_db_utils import init_test_schema, insert_test_session

# ─── 辅助函数 ────────────────────────────────────────────────────────────────


def _make_conn() -> sqlite3.Connection:
    """创建带有 sessions schema 的内存 SQLite 连接。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_test_schema(conn)
    return conn


def _insert(conn: sqlite3.Connection, session_id: str, title: str, **kw) -> SessionSummary:
    """插入单个会话并返回摘要对象。"""
    s = SessionSummary(
        agent="claude_code",
        session_id=session_id,
        title=title,
        project_key="proj-test",
        project_name="test",
        cwd="/tmp/test",
        started_at="2026-05-01T10:00:00Z",
        ended_at="2026-05-01T10:30:00Z",
        duration_seconds=1800,
        **kw,
    )
    insert_test_session(conn, s)
    return s


# ─── 不区分大小写的标题搜索（现有行为，回归防护） ────────


class TestTitleCaseInsensitive:
    """验证标题 LIKE 不区分大小写（SQLite LIKE 默认行为）。"""

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_lowercase_query_matches_mixed_case_title(self):
        with closing(_make_conn()) as conn:
            _insert(conn, session_id="sess-001", title="MyProject Alpha Build")

            results = list_sessions(conn, title_like="myproject")
        assert len(results) == 1
        assert results[0].title == "MyProject Alpha Build"

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_uppercase_query_matches_mixed_case_title(self):
        with closing(_make_conn()) as conn:
            _insert(conn, session_id="sess-002", title="debug session for beta")

            results = list_sessions(conn, title_like="DEBUG")
        assert len(results) == 1

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_partial_case_insensitive_substring(self):
        with closing(_make_conn()) as conn:
            _insert(conn, session_id="sess-003", title="Feipi Session Browser")

            # 混合大小写查询
            results = list_sessions(conn, title_like="sSiOn")
        assert len(results) == 1

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_no_match_for_unrelated_query(self):
        with closing(_make_conn()) as conn:
            _insert(conn, session_id="sess-004", title="Some Random Title")

            results = list_sessions(conn, title_like="foobar")
        assert len(results) == 0

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_count_sessions_case_insensitive(self):
        with closing(_make_conn()) as conn:
            _insert(conn, session_id="sess-c1", title="Alpha Session")
            _insert(conn, session_id="sess-c2", title="Beta Session")
            _insert(conn, session_id="sess-c3", title="alpha session two")

            assert count_sessions(conn, title_like="alpha") == 2
            assert count_sessions(conn, title_like="ALPHA") == 2
            assert count_sessions(conn, title_like="beta") == 1


# ─── Session ID substring search (S-13) ─────────────────────────────────────


class TestSessionIdCaseInsensitiveSubstring:
    """S-13: q 参数应同时匹配 title 和 session_id，大小写不敏感。"""

    MIXED_CASE_SID = "AdB90C9C-3C4B-4318"

    def setup_method(self):
        self.conn = _make_conn()
        _insert(
            self.conn,
            session_id=self.MIXED_CASE_SID,
            title="Unrelated Title ZZZ",
        )

    def teardown_method(self):
        self.conn.close()

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_lowercase_session_id_matches(self):
        """adb90c9c（小写）应匹配 AdB90C9C-3C4B-4318。"""
        results = list_sessions(self.conn, title_like="adb90c9c")
        assert len(results) == 1
        assert results[0].session_id == self.MIXED_CASE_SID

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_uppercase_session_id_matches(self):
        """ADB90C9C（大写）应匹配 AdB90C9C-3C4B-4318。"""
        results = list_sessions(self.conn, title_like="ADB90C9C")
        assert len(results) == 1
        assert results[0].session_id == self.MIXED_CASE_SID

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_mixed_case_session_id_matches(self):
        """AdB90C9C（混合大小写）应匹配 AdB90C9C-3C4B-4318。"""
        results = list_sessions(self.conn, title_like="AdB90C9C")
        assert len(results) == 1

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_session_id_substring_matches(self):
        """3c4b（小写子串）应匹配 session_id。"""
        results = list_sessions(self.conn, title_like="3c4b")
        assert len(results) == 1

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_unrelated_query_no_match(self):
        """不相关的查询不应匹配。"""
        results = list_sessions(self.conn, title_like="notexist123")
        assert len(results) == 0

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_count_session_id_match(self):
        """count_sessions 也应匹配 session_id。"""
        count = count_sessions(self.conn, title_like="adb90c9c")
        assert count == 1


# ─── 双重匹配：title 或 session_id 均可匹配 ──────────────────────────


class TestDualMatchTitleOrSessionId:
    """验证查询匹配 title 或 session_id。"""

    def setup_method(self):
        self.conn = _make_conn()
        _insert(self.conn, session_id="SID-AAAA-1111", title="Frontend Refactor Q2")
        _insert(self.conn, session_id="SID-BBBB-2222", title="Backend API Gateway")

    def teardown_method(self):
        self.conn.close()

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_match_by_title_only(self):
        results = list_sessions(self.conn, title_like="Frontend")
        assert len(results) == 1
        assert results[0].session_id == "SID-AAAA-1111"

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_match_by_session_id_only(self):
        results = list_sessions(self.conn, title_like="bbbb")
        assert len(results) == 1
        assert results[0].session_id == "SID-BBBB-2222"

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_no_false_positive(self):
        results = list_sessions(self.conn, title_like="nonexistent")
        assert len(results) == 0

    @pytest.mark.contract_case("DATA-INDEX-012")
    def test_count_dual_match(self):
        # 应返回 2，因为 title 和 session_id 都可搜索
        count = count_sessions(self.conn, title_like="API")
        assert count == 1
