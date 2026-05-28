"""Bad JSON 隔离测试，针对 Claude Code 索引器。

验证：
- 坏 JSON 行不会导致解析器崩溃（隔离）
- 有效的 JSON 行仍能被正确解析和索引
- 诊断信息记录坏行及其行号
- 不会抛出未捕获的异常
- 会话仍会被索引，并附带诊断元数据

对应 V9 长跑 task 054。
"""

import pytest
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# ─── 常量 ──────────────────────────────────────────────────────────────

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "index_corpus" / "bad_json_session"

# fixture 中已知的坏行（从 1 开始的行号）
BAD_LINE_NUMBERS = {2, 4, 6}
GOOD_LINE_COUNT = 6  # fixture 中包含 6 个有效的 JSON 对象


# ─── 辅助函数 ────────────────────────────────────────────────────────────

def _setup_claude_env(data_dir: str):
    """设置 CLAUDE_DATA_DIR 并重新加载依赖模块。"""
    old = os.environ.get("CLAUDE_DATA_DIR", None)
    os.environ["CLAUDE_DATA_DIR"] = data_dir

    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.config"):
            del sys.modules[_mod]
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]
        if _mod.startswith("session_browser.index.indexer"):
            del sys.modules[_mod]

    return old


def _restore_claude_env(old: str | None):
    """恢复原始的 CLAUDE_DATA_DIR。"""
    if old is not None:
        os.environ["CLAUDE_DATA_DIR"] = old
    else:
        os.environ.pop("CLAUDE_DATA_DIR", None)


def _run_full_scan(data_dir: str, db_path: str) -> dict:
    """对 data_dir 运行 full_scan()，返回扫描统计。"""
    old_env = _setup_claude_env(data_dir)
    try:
        from session_browser.index.indexer import full_scan

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        result = full_scan(conn, verbose=False, agent="claude_code")
        conn.close()
        return result
    finally:
        _restore_claude_env(old_env)


# ─── 测试：jsonl_reader 层级 ─────────────────────────────────────────────

class TestJsonlReaderBadJsonIsolation:
    """验证 parse_jsonl_events 对坏 JSON 行的隔离能力。"""

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_bad_lines_do_not_crash_parser(self, tmp_path):
        """解析包含坏 JSON 行的文件时不应抛出异常。"""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        # 将 fixture 复制到临时位置
        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        assert src.exists(), "Fixture file missing"

        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # 必须正常完成而不抛出异常
        assert events is not None
        assert diagnostics is not None

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_good_lines_still_parsed(self, tmp_path):
        """有效的 JSON 行仍应产生事件。"""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # fixture 中有 6 个有效的 JSON 对象
        assert diagnostics.events_parsed == GOOD_LINE_COUNT, (
            f"Expected {GOOD_LINE_COUNT} parsed events, got {diagnostics.events_parsed}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_diagnostics_record_bad_lines(self, tmp_path):
        """诊断信息应记录坏/不可解析的行。"""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # fixture 中有 3 个已知的坏行
        assert diagnostics.events_skipped == len(BAD_LINE_NUMBERS), (
            f"Expected {len(BAD_LINE_NUMBERS)} skipped events, got {diagnostics.events_skipped}"
        )

        # 坏行号应与预期集合匹配
        bad_line_nos = {issue.line_no for issue in diagnostics.issues}
        assert bad_line_nos == BAD_LINE_NUMBERS, (
            f"Expected bad lines at {BAD_LINE_NUMBERS}, got {bad_line_nos}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_bad_json_issues_have_correct_severity(self, tmp_path):
        """每个坏 JSON 问题都应标记为 ERROR 严重级别。"""
        from session_browser.sources.jsonl_reader import (
            parse_jsonl_events, ParseIssue, ParseSeverity,
        )

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        for issue in diagnostics.issues:
            assert issue.issue == ParseIssue.BAD_JSON
            assert issue.severity == ParseSeverity.ERROR

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_bad_json_issues_have_preview(self, tmp_path):
        """每个问题都应携带 offending 行的预览。"""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        for issue in diagnostics.issues:
            assert issue.preview != "", f"Issue at line {issue.line_no} has empty preview"
            assert len(issue.preview) > 0

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_no_uncaught_exception(self, tmp_path):
        """解析器绝不能对坏 JSON 抛出未捕获的异常。"""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"

        # 应正常完成 —— 如果抛出异常则测试失败
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        # 验证至少解析到了一些事件
        assert len(events) > 0, "Expected at least some events to be parsed"

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_event_types_are_correct(self, tmp_path):
        """解析的事件应具有正确的 'type' 字段。"""
        from session_browser.sources.jsonl_reader import parse_jsonl_events

        src = FIXTURE_ROOT / "projects" / "bad-proj" / "bad-sess-001.jsonl"
        events, diagnostics = parse_jsonl_events(src, verbose=False)

        event_types = [ev.get("type") for ev in events]
        assert "user" in event_types, "Expected at least one 'user' event"
        assert "assistant" in event_types, "Expected at least one 'assistant' event"


# ─── 测试：full scan / indexer 层级 ──────────────────────────────────────

class TestBadJsonSessionIndexing:
    """验证包含坏 JSON 行的会话仍能被索引。"""

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_indexed_despite_bad_json(self, tmp_path):
        """full_scan() 应索引包含坏 JSON 行的会话。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")

        # 不应抛出异常
        result = _run_full_scan(str(data_dir), db_path)

        assert result["claude_count"] == 1, (
            f"Expected 1 Claude session, got {result['claude_count']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_key_present_in_db(self, tmp_path):
        """坏 JSON 会话应出现在 sessions 表中。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT session_key FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None, "Session key claude_code:bad-sess-001 not found in index"

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_has_valid_title(self, tmp_path):
        """被索引的会话应具有从用户消息派生的标题。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT title FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        assert "bug" in row["title"].lower(), (
            f"Expected title to contain 'bug', got '{row['title']}'"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_has_correct_message_counts(self, tmp_path):
        """消息计数应仅反映有效（已解析）的行。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT user_message_count, assistant_message_count FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        # Fixture: 1 条用户消息带有人类文本（第 1 行）。
        # 第 7 行是用户事件但仅携带 tool_result（无人类文本），
        # 因此 _extract_user_text 返回空值，user_count 保持为 1。
        assert row["user_message_count"] == 1, (
            f"Expected 1 user message, got {row['user_message_count']}"
        )
        # Fixture: 4 条 assistant 消息片段（第 3, 5, 8, 9 行）
        # 但 _assistant_records 按 message id 合并，所以有 4 条不同记录
        assert row["assistant_message_count"] == 4, (
            f"Expected 4 assistant messages, got {row['assistant_message_count']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_session_has_token_data_from_good_lines(self, tmp_path):
        """Token 计数应仅从有效行派生。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT input_tokens, output_tokens FROM sessions WHERE session_key = ?",
            ("claude_code:bad-sess-001",),
        ).fetchone()
        conn.close()

        assert row is not None
        # input_tokens: 150 + 200 + 180 + 100 = 630（来自 4 条 assistant 记录）
        assert row["input_tokens"] == 630, (
            f"Expected 630 input tokens, got {row['input_tokens']}"
        )
        # output_tokens: 80 + 60 + 70 + 40 = 250
        assert row["output_tokens"] == 250, (
            f"Expected 250 output tokens, got {row['output_tokens']}"
        )

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_scan_log_records_success(self, tmp_path):
        """scan_log 应显示成功扫描，即使存在坏 JSON。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        log = conn.execute(
            "SELECT * FROM scan_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        assert log is not None
        assert log["status"] == "done", f"Expected status 'done', got '{log['status']}'"
        assert log["claude_count"] == 1

    @pytest.mark.contract_case("DATA-INDEX-006")
    def test_no_other_sessions_indexed(self, tmp_path):
        """应仅索引 fixture 会话 —— 不应泄漏。"""
        data_dir = tmp_path / "claude_data"
        shutil.copytree(str(FIXTURE_ROOT), str(data_dir))

        db_path = str(tmp_path / "index.sqlite")
        _run_full_scan(str(data_dir), db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()

        assert count == 1, f"Expected exactly 1 session, got {count}"
