"""Codex 解析器测试。"""
import pytest
import json
from pathlib import Path


@pytest.mark.contract_case("DATA-SOURCE-005", "DATA-SOURCE-006", "DATA-SOURCE-007")
def test_parse_session_index_empty_when_missing():
    """测试无数据目录时 parse_session_index 返回空列表。"""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            result = codex.parse_session_index()
            assert result == []
        finally:
            codex.CODEX_DATA_DIR = original


@pytest.mark.contract_case("DATA-SOURCE-005", "DATA-SOURCE-006", "DATA-SOURCE-007")
def test_read_threads_db_empty_when_missing():
    """测试无数据库时 read_threads_db 返回空字典。"""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            result = codex.read_threads_db()
            assert result == {}
        finally:
            codex.CODEX_DATA_DIR = original


@pytest.mark.contract_case("DATA-SOURCE-005", "DATA-SOURCE-006", "DATA-SOURCE-007")
def test_session_file_search():
    """测试 _find_session_file 遍历层级目录。"""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            # 创建模拟会话文件
            session_dir = Path(tmpdir) / "sessions" / "2026" / "03" / "28"
            session_dir.mkdir(parents=True)
            session_file = session_dir / "rollout-2026-03-28T15-54-11-019d336f.jsonl"
            session_file.touch()

            result = codex._find_session_file("019d336f")
            assert result is not None
            assert result == session_file
        finally:
            codex.CODEX_DATA_DIR = original
