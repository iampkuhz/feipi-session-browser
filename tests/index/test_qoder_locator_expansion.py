"""Qoder 定位器路径展开测试。

验证 _find_session_file 和 _locate_qoder_session_file 能正确：
1. 将短 ID 别名解析为完整 UUID，然后搜索 projects/。
2. 在 projects/ 中找到完整 UUID 会话（直接匹配 + 递归搜索）。
3. 通过递归遍历在 cache/projects/ 中找到会话。
4. 处理空的或过期的 project_key（旧索引场景）。

测试使用 monkeypatch 的临时 QODER_DATA_DIR —— 不涉及真实用户数据。
"""

from __future__ import annotations

import pytest
import json
import os
import sys
from pathlib import Path

# ─── 常量 ──────────────────────────────────────────────────────────────

FULL_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
SHORT_ID = "a1b2c3d4"
PROJECT_NAME = "myproj"

# 最小化 Qoder CLI JSONL（含时间戳、type 字段、usage）
CLI_JSONL_LINES = [
    json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "Hello"},
        "timestamp": "2026-05-01T10:00:00.000Z",
        "cwd": "/tmp/myproj",
        "entrypoint": "cli",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "model": "qwen3.6-plus",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi!"}],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        },
        "timestamp": "2026-05-01T10:00:05.000Z",
        "sessionId": FULL_UUID,
        "version": "1.0.0",
    }),
]
CLI_JSONL_CONTENT = "\n".join(CLI_JSONL_LINES) + "\n"

# 缓存格式的最小化 Qoder JSONL（无时间戳、role 字段）
CACHE_JSONL_LINES = [
    json.dumps({"role": "user", "message": {"content": "Hello from cache"}}),
    json.dumps({"role": "assistant", "message": {"content": [{"type": "text", "text": "Cache hi"}]}}),
]
CACHE_JSONL_CONTENT = "\n".join(CACHE_JSONL_LINES) + "\n"


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_qoder_env(data_dir: str):
    """设置 QODER_DATA_DIR 并重新加载依赖模块。"""
    old = os.environ.get("QODER_DATA_DIR", None)
    os.environ["QODER_DATA_DIR"] = data_dir

    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.config"):
            del sys.modules[_mod]
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.sources"):
            del sys.modules[_mod]
    for _mod in list(sys.modules):
        if _mod.startswith("session_browser.index.indexer"):
            del sys.modules[_mod]

    return old


def _restore_qoder_env(old: str | None):
    """恢复原始的 QODER_DATA_DIR。"""
    if old is not None:
        os.environ["QODER_DATA_DIR"] = old
    else:
        os.environ.pop("QODER_DATA_DIR", None)


def _reload_qoder_module():
    """环境变量变更后重新加载 Qoder 源模块。"""
    for _mod in list(sys.modules):
        if _mod == "session_browser.sources.qoder" or _mod.startswith("session_browser.sources.qoder"):
            del sys.modules[_mod]


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def full_uuid_in_projects(tmp_path: Path) -> Path:
    """创建 projects/<project>/<FULL_UUID>.jsonl —— CLI 会话。"""
    data_dir = tmp_path / "qoder_data"
    projects_dir = data_dir / "projects" / PROJECT_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{FULL_UUID}.jsonl").write_text(CLI_JSONL_CONTENT)
    return data_dir


@pytest.fixture()
def short_id_in_cache_only(tmp_path: Path) -> Path:
    """创建 cache/projects/<project>/conversation-history/<SHORT_ID>/<SHORT_ID>.jsonl
    且不在 projects/ 中创建对应条目。"""
    data_dir = tmp_path / "qoder_data"
    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / SHORT_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SHORT_ID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir


@pytest.fixture()
def both_full_and_short(tmp_path: Path) -> Path:
    """为同一会话同时创建 projects/（完整 UUID）和 cache/（短 ID）。"""
    data_dir = tmp_path / "qoder_data"
    projects_dir = data_dir / "projects" / PROJECT_NAME
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{FULL_UUID}.jsonl").write_text(CLI_JSONL_CONTENT)

    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / SHORT_ID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{SHORT_ID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir


@pytest.fixture()
def cache_only_full_uuid(tmp_path: Path) -> Path:
    """仅在 cache/projects/ 中创建完整 UUID 会话文件（无 projects/）。"""
    data_dir = tmp_path / "qoder_data"
    cache_dir = data_dir / "cache" / "projects" / PROJECT_NAME / "conversation-history" / FULL_UUID
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{FULL_UUID}.jsonl").write_text(CACHE_JSONL_CONTENT)
    return data_dir


# ─── 测试：_find_session_file (qoder.py) ──────────────────────────────────

class TestFindSessionFile:
    """qoder._find_session_file 的测试。"""

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_full_uuid_direct_match_in_projects(self, full_uuid_in_projects):
        """projects/ 中的完整 UUID 会话应能通过直接匹配找到。"""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, FULL_UUID)
            assert result is not None, "Should find full UUID session in projects/"
            assert result.name == f"{FULL_UUID}.jsonl"
            assert "projects" in str(result)
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_short_id_resolved_to_full_uuid(self, both_full_and_short):
        """短 ID 应解析为完整 UUID 并找到 projects/ 中的文件。"""
        data_dir = both_full_and_short
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None, "Short ID should resolve and find session"
            assert result.name == f"{FULL_UUID}.jsonl"
            # 应优先选择 projects/ 而非 cache
            assert "projects" in str(result) and "cache" not in str(result).split("projects")[0].split("/")[-1:]
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_cache_only_short_id_found(self, short_id_in_cache_only):
        """仅在 cache/ 中且使用短 ID 的会话仍应能被定位。"""
        data_dir = short_id_in_cache_only
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None, "Should find cache-only session"
            assert result.name == f"{SHORT_ID}.jsonl"
            assert "cache" in str(result)
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_empty_project_key_still_finds_session(self, full_uuid_in_projects):
        """当 project_key 为空（旧索引）时，递归搜索应能找到会话。"""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file("", FULL_UUID)
            assert result is not None, "Should find session even with empty project_key"
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_cache_only_full_uuid_found(self, cache_only_full_uuid):
        """仅在 cache/ 中的完整 UUID 会话应能通过递归遍历找到。"""
        data_dir = cache_only_full_uuid
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, FULL_UUID)
            assert result is not None, "Should find cache-only full UUID session"
            assert result.name == f"{FULL_UUID}.jsonl"
            assert "cache" in str(result)
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_no_session_returns_none(self, tmp_path):
        """不存在的会话应返回 None，而非抛出异常。"""
        data_dir = tmp_path / "qoder_empty"
        data_dir.mkdir(parents=True)
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.sources.qoder import _find_session_file

            result = _find_session_file(PROJECT_NAME, "nonexistent-uuid")
            assert result is None
        finally:
            _restore_qoder_env(old)


# ─── 测试：_locate_qoder_session_file (indexer.py) ────────────────────────

class TestLocateQoderSessionFile:
    """indexer._locate_qoder_session_file 的测试。"""

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_full_uuid_in_projects(self, full_uuid_in_projects):
        """定位器应在 projects/ 中找到完整 UUID 会话。"""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file(PROJECT_NAME, FULL_UUID)
            assert result is not None
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_short_id_resolved_in_indexer(self, both_full_and_short):
        """索引器定位器也应解析短 ID -> 完整 UUID。"""
        data_dir = both_full_and_short
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_cache_fallback_in_indexer(self, short_id_in_cache_only):
        """索引器定位器应对仅存在于 cache/ 的会话回退到 cache。"""
        data_dir = short_id_in_cache_only
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file(PROJECT_NAME, SHORT_ID)
            assert result is not None
            assert "cache" in str(result)
        finally:
            _restore_qoder_env(old)

    @pytest.mark.contract_case("DATA-INDEX-010")
    def test_empty_project_key_in_indexer(self, full_uuid_in_projects):
        """索引器定位器即使 project_key 为空也应找到会话。"""
        data_dir = full_uuid_in_projects
        old = _setup_qoder_env(str(data_dir))
        try:
            _reload_qoder_module()
            from session_browser.index.indexer import _locate_qoder_session_file

            result = _locate_qoder_session_file("", FULL_UUID)
            assert result is not None
            assert result.name == f"{FULL_UUID}.jsonl"
        finally:
            _restore_qoder_env(old)
