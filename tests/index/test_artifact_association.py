"""Artifact association 和幂等 repair 测试。

覆盖：
- 只有 verified WRITTEN/UNCHANGED 结果可以关联
- FAILED/RETRYABLE 不写入 DB
- 重复 repair 幂等性
- DB failure 不删除有效 artifact
- corrupt artifact 不进入 index
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from session_browser.domain.models import SessionSummary
from session_browser.index.schema import init_schema, ensure_session_artifacts_schema
from session_browser.index.writers import (
    associate_batch_results,
    associate_verified_artifact,
    repair_artifact_associations,
    safe_upsert_after_bridge,
    upsert_session,
    upsert_session_artifact,
    validate_artifact_row,
)
from session_browser.normalized.schema import NORMALIZED_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _FakeStatus(Enum):
    """模拟 Java bridge ResultStatus。"""

    WRITTEN = 'WRITTEN'
    UNCHANGED = 'UNCHANGED'
    RETRYABLE = 'RETRYABLE'
    FAILED = 'FAILED'


@dataclass
class _FakeResult:
    """模拟 Java bridge BatchResult。"""

    request_id: str
    status: _FakeStatus
    session_key: str = ''
    artifact_path: str = ''
    content_hash: str = ''
    error: str = ''


_ARTIFACT_TYPE = 'normalized_session_json'


def _minimal_normalized(agent: str, session_id: str) -> dict:
    """构建最小合法的 normalized artifact payload。"""
    return {
        'schema_version': NORMALIZED_SCHEMA_VERSION,
        'agent': agent,
        'source': {'files': []},
        'session': {
            'session_key': f'{agent}:{session_id}',
            'session_id': session_id,
            'agent': agent,
        },
        'calls': [],
        'tool_executions': [],
        'diagnostics': [],
    }


def _write_artifact(
    index_dir: Path,
    agent: str,
    session_id: str,
    payload: dict | None = None,
    *,
    corrupt: bool = False,
) -> tuple[Path, int, str]:
    """写入一个 normalized artifact 文件，返回 (path, size, hash)。"""
    if payload is None:
        payload = _minimal_normalized(agent, session_id)
    safe_sid = session_id.replace('/', '_').replace(':', '_')
    artifact_path = (
        index_dir / 'artifacts' / 'normalized-sessions' / agent / f'{safe_sid}.json'
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        artifact_path.write_text('not valid json {{{', encoding='utf-8')
    else:
        raw = json.dumps(payload, ensure_ascii=False) + '\n'
        artifact_path.write_text(raw, encoding='utf-8')
    size = artifact_path.stat().st_size
    content_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    return artifact_path, size, content_hash


def _setup_db(tmp_path: Path) -> sqlite3.Connection:
    """创建测试 DB 并初始化 schema。"""
    db_path = tmp_path / 'index.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    init_schema(conn)
    return conn


def _insert_session(conn: sqlite3.Connection, agent: str, session_id: str) -> None:
    """插入一条 session 行以满足外键约束。"""
    summary = SessionSummary(
        agent=agent,
        session_id=session_id,
        title='test',
        project_key='/tmp/test',
        project_name='test',
        cwd='/tmp/test',
        started_at='2026-06-10T00:00:00+00:00',
        ended_at='2026-06-10T00:01:00+00:00',
    )
    upsert_session(conn, summary)


# ---------------------------------------------------------------------------
# Artifact association 测试
# ---------------------------------------------------------------------------


class TestAssociateVerifiedArtifact:
    """associate_verified_artifact 只允许 WRITTEN/UNCHANGED 状态。"""

    def test_written_status_associates(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'sess-1')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'sess-1')

        result = associate_verified_artifact(
            conn,
            session_key='codex:sess-1',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
            bridge_status='WRITTEN',
        )
        conn.commit()

        assert result is True
        row = conn.execute(
            'SELECT * FROM session_artifacts WHERE session_key = ?',
            ('codex:sess-1',),
        ).fetchone()
        assert row is not None
        assert row['validation_status'] == 'ok'
        assert row['content_hash'] == content_hash
        conn.close()

    def test_unchanged_status_associates(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'sess-2')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'sess-2')

        result = associate_verified_artifact(
            conn,
            session_key='codex:sess-2',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
            bridge_status='UNCHANGED',
        )
        conn.commit()

        assert result is True
        row = conn.execute(
            'SELECT validation_status FROM session_artifacts WHERE session_key = ?',
            ('codex:sess-2',),
        ).fetchone()
        assert row['validation_status'] == 'ok'
        conn.close()

    def test_failed_status_does_not_associate(self, tmp_path):
        conn = _setup_db(tmp_path)
        _insert_session(conn, 'codex', 'sess-3')

        result = associate_verified_artifact(
            conn,
            session_key='codex:sess-3',
            artifact_type=_ARTIFACT_TYPE,
            path='/nonexistent/path.json',
            bridge_status='FAILED',
        )
        conn.commit()

        assert result is False
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM session_artifacts WHERE session_key = ?',
            ('codex:sess-3',),
        ).fetchone()
        assert row['cnt'] == 0
        conn.close()

    def test_retryable_status_does_not_associate(self, tmp_path):
        conn = _setup_db(tmp_path)
        _insert_session(conn, 'codex', 'sess-4')

        result = associate_verified_artifact(
            conn,
            session_key='codex:sess-4',
            artifact_type=_ARTIFACT_TYPE,
            path='/nonexistent/path.json',
            bridge_status='RETRYABLE',
        )
        conn.commit()

        assert result is False
        conn.close()


class TestAssociateBatchResults:
    """associate_batch_results 批量处理 bridge 结果。"""

    def test_batch_filters_by_status(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'batch-1')
        _insert_session(conn, 'codex', 'batch-2')
        _insert_session(conn, 'codex', 'batch-3')

        p1, s1, h1 = _write_artifact(index_dir, 'codex', 'batch-1')
        p2, s2, h2 = _write_artifact(index_dir, 'codex', 'batch-2')

        results = [
            _FakeResult('r1', _FakeStatus.WRITTEN, 'codex:batch-1', str(p1), h1),
            _FakeResult('r2', _FakeStatus.UNCHANGED, 'codex:batch-2', str(p2), h2),
            _FakeResult('r3', _FakeStatus.FAILED, 'codex:batch-3', '', '', 'error'),
        ]

        stats = associate_batch_results(conn, results)
        conn.commit()

        assert stats['associated'] == 2
        assert stats['skipped'] == 1

        # batch-1 和 batch-2 已关联
        row1 = conn.execute(
            'SELECT validation_status FROM session_artifacts WHERE session_key = ?',
            ('codex:batch-1',),
        ).fetchone()
        assert row1['validation_status'] == 'ok'

        row2 = conn.execute(
            'SELECT validation_status FROM session_artifacts WHERE session_key = ?',
            ('codex:batch-2',),
        ).fetchone()
        assert row2['validation_status'] == 'ok'

        # batch-3 未关联
        row3 = conn.execute(
            'SELECT COUNT(*) as cnt FROM session_artifacts WHERE session_key = ?',
            ('codex:batch-3',),
        ).fetchone()
        assert row3['cnt'] == 0
        conn.close()


# ---------------------------------------------------------------------------
# 幂等 repair 测试
# ---------------------------------------------------------------------------


class TestRepairIdempotency:
    """重复 repair 不改变正确结果。"""

    def test_repair_ok_row_unchanged(self, tmp_path):
        """已经 ok 的行 repair 后不变。"""
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'rep-1')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'rep-1')

        # 先正常关联
        upsert_session_artifact(
            conn,
            session_key='codex:rep-1',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
            validation_status='ok',
        )
        conn.commit()

        # 第一次 repair
        stats1 = repair_artifact_associations(conn)
        conn.commit()
        assert stats1['repaired'] == 0
        assert stats1['removed'] == 0

        # 第二次 repair（幂等）
        stats2 = repair_artifact_associations(conn)
        conn.commit()
        assert stats2['repaired'] == 0
        assert stats2['removed'] == 0

        # 行仍然存在且状态不变
        row = conn.execute(
            'SELECT validation_status, content_hash FROM session_artifacts '
            'WHERE session_key = ?',
            ('codex:rep-1',),
        ).fetchone()
        assert row['validation_status'] == 'ok'
        assert row['content_hash'] == content_hash
        conn.close()

    def test_repair_marks_stale_row_as_ok(self, tmp_path):
        """validation_status 为空但文件完好的行，repair 后标记为 ok。"""
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'rep-2')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'rep-2')

        # 手动插入一行 validation_status 为空的记录
        upsert_session_artifact(
            conn,
            session_key='codex:rep-2',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
            validation_status='',
        )
        conn.commit()

        stats = repair_artifact_associations(conn)
        conn.commit()
        assert stats['repaired'] == 1
        assert stats['removed'] == 0

        row = conn.execute(
            'SELECT validation_status FROM session_artifacts WHERE session_key = ?',
            ('codex:rep-2',),
        ).fetchone()
        assert row['validation_status'] == 'ok'
        conn.close()

    def test_repair_idempotent_after_multiple_calls(self, tmp_path):
        """多次 repair 结果一致。"""
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'rep-3')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'rep-3')

        upsert_session_artifact(
            conn,
            session_key='codex:rep-3',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
            validation_status='ok',
        )
        conn.commit()

        # 连续调用 3 次 repair
        results = []
        for _ in range(3):
            stats = repair_artifact_associations(conn)
            conn.commit()
            results.append(stats)

        # 所有结果一致
        for stats in results:
            assert stats['repaired'] == 0
            assert stats['removed'] == 0
        conn.close()


# ---------------------------------------------------------------------------
# DB failure 恢复测试
# ---------------------------------------------------------------------------


class TestDBFailureRecovery:
    """DB failure 不删除有效 artifact。"""

    def test_missing_artifact_row_removed(self, tmp_path):
        """DB 行指向不存在的 artifact → 行被删除（下次 scan 重建）。"""
        conn = _setup_db(tmp_path)
        _insert_session(conn, 'codex', 'fail-1')

        # 手动插入指向不存在路径的行
        upsert_session_artifact(
            conn,
            session_key='codex:fail-1',
            artifact_type=_ARTIFACT_TYPE,
            path='/nonexistent/path.json',
            size_bytes=100,
        )
        conn.commit()

        stats = repair_artifact_associations(conn)
        conn.commit()

        assert stats['removed'] == 1
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM session_artifacts WHERE session_key = ?',
            ('codex:fail-1',),
        ).fetchone()
        assert row['cnt'] == 0
        conn.close()

    def test_corrupt_artifact_not_in_index(self, tmp_path):
        """corrupt artifact 不入 index：repair 后行被删除。"""
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'fail-2')
        artifact_path, _, _ = _write_artifact(
            index_dir, 'codex', 'fail-2', corrupt=True
        )

        # 插入指向 corrupt 文件的行
        upsert_session_artifact(
            conn,
            session_key='codex:fail-2',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=999,  # size 不匹配 → corrupt
        )
        conn.commit()

        stats = repair_artifact_associations(conn)
        conn.commit()

        assert stats['removed'] == 1
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM session_artifacts WHERE session_key = ?',
            ('codex:fail-2',),
        ).fetchone()
        assert row['cnt'] == 0

        # artifact 文件仍在磁盘上（不删除有效文件）
        assert artifact_path.exists()
        conn.close()

    def test_db_commit_failure_preserves_artifact_file(self, tmp_path):
        """DB commit 失败时，artifact 文件不被删除。

        safe_upsert_after_bridge 只执行 upsert，不执行 delete。
        如果 commit 失败，artifact 文件仍在磁盘上。
        """
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'fail-3')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'fail-3')

        # 模拟 bridge 成功但 commit 失败的场景
        safe_upsert_after_bridge(
            conn,
            session_key='codex:fail-3',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
        )
        # 不 commit → 模拟 DB 失败

        # artifact 文件仍在
        assert artifact_path.exists()

        # 模拟下次 scan 的 repair：先 commit 当前状态（回滚未 commit 的写入）
        conn.rollback()

        # 行不存在（因为 commit 失败了）
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM session_artifacts WHERE session_key = ?',
            ('codex:fail-3',),
        ).fetchone()
        assert row['cnt'] == 0

        # 但 artifact 文件仍然存在
        assert artifact_path.exists()

        # 下次 scan 的 repair 不会删除有效文件
        stats = repair_artifact_associations(conn)
        conn.commit()
        assert stats['removed'] == 0  # 没有行可以 repair
        assert artifact_path.exists()  # 文件仍在
        conn.close()

    def test_repair_restores_after_db_loss(self, tmp_path):
        """DB 行丢失后，repair 通过 disk 上的有效 artifact 恢复关联。"""
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'fail-4')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'fail-4')

        # 先正常写入
        upsert_session_artifact(
            conn,
            session_key='codex:fail-4',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
            validation_status='ok',
        )
        conn.commit()

        # 模拟 DB 行丢失
        conn.execute("DELETE FROM session_artifacts WHERE session_key = 'codex:fail-4'")
        conn.commit()

        # 手动重新关联（模拟 scan 的 persist_current_reference 路径）
        safe_upsert_after_bridge(
            conn,
            session_key='codex:fail-4',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
        )
        conn.commit()

        # repair 验证行状态
        stats = repair_artifact_associations(conn)
        conn.commit()
        assert stats['repaired'] == 0  # 已经是 ok
        assert stats['removed'] == 0

        row = conn.execute(
            'SELECT validation_status FROM session_artifacts WHERE session_key = ?',
            ('codex:fail-4',),
        ).fetchone()
        assert row['validation_status'] == 'ok'
        conn.close()


# ---------------------------------------------------------------------------
# validate_artifact_row 测试
# ---------------------------------------------------------------------------


class TestValidateArtifactRow:
    """validate_artifact_row 正确判断 artifact 完整性。"""

    def test_valid_artifact_returns_ok(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'val-1')
        artifact_path, size, content_hash = _write_artifact(index_dir, 'codex', 'val-1')

        upsert_session_artifact(
            conn,
            session_key='codex:val-1',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash=content_hash,
        )
        conn.commit()

        row = conn.execute(
            'SELECT * FROM session_artifacts WHERE session_key = ?',
            ('codex:val-1',),
        ).fetchone()
        assert validate_artifact_row(conn, row) == 'ok'
        conn.close()

    def test_missing_file_returns_missing(self, tmp_path):
        conn = _setup_db(tmp_path)
        _insert_session(conn, 'codex', 'val-2')

        upsert_session_artifact(
            conn,
            session_key='codex:val-2',
            artifact_type=_ARTIFACT_TYPE,
            path='/no/such/file.json',
            size_bytes=100,
        )
        conn.commit()

        row = conn.execute(
            'SELECT * FROM session_artifacts WHERE session_key = ?',
            ('codex:val-2',),
        ).fetchone()
        assert validate_artifact_row(conn, row) == 'missing'
        conn.close()

    def test_corrupt_json_returns_corrupt(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'val-3')
        artifact_path, _, _ = _write_artifact(
            index_dir, 'codex', 'val-3', corrupt=True
        )

        upsert_session_artifact(
            conn,
            session_key='codex:val-3',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=artifact_path.stat().st_size,
        )
        conn.commit()

        row = conn.execute(
            'SELECT * FROM session_artifacts WHERE session_key = ?',
            ('codex:val-3',),
        ).fetchone()
        assert validate_artifact_row(conn, row) == 'corrupt'
        conn.close()

    def test_size_mismatch_returns_corrupt(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'val-4')
        artifact_path, _, _ = _write_artifact(index_dir, 'codex', 'val-4')

        upsert_session_artifact(
            conn,
            session_key='codex:val-4',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=9999,  # 不匹配
        )
        conn.commit()

        row = conn.execute(
            'SELECT * FROM session_artifacts WHERE session_key = ?',
            ('codex:val-4',),
        ).fetchone()
        assert validate_artifact_row(conn, row) == 'corrupt'
        conn.close()

    def test_hash_mismatch_returns_corrupt(self, tmp_path):
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'val-5')
        artifact_path, size, _ = _write_artifact(index_dir, 'codex', 'val-5')

        upsert_session_artifact(
            conn,
            session_key='codex:val-5',
            artifact_type=_ARTIFACT_TYPE,
            path=str(artifact_path),
            size_bytes=size,
            content_hash='deadbeef' * 8,  # 错误的 hash
        )
        conn.commit()

        row = conn.execute(
            'SELECT * FROM session_artifacts WHERE session_key = ?',
            ('codex:val-5',),
        ).fetchone()
        assert validate_artifact_row(conn, row) == 'corrupt'
        conn.close()


# ---------------------------------------------------------------------------
# Schema 迁移测试
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """ensure_session_artifacts_schema 幂等迁移新增列。"""

    def test_new_columns_added_to_existing_table(self, tmp_path):
        """旧表（缺少新列）调用 ensure 后补齐。"""
        db_path = tmp_path / 'index.sqlite'
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')

        # 手动创建不含新列的旧表
        conn.executescript("""
            CREATE TABLE sessions (
                session_key TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                project_key TEXT NOT NULL DEFAULT '',
                project_name TEXT NOT NULL DEFAULT '',
                cwd TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                ended_at TEXT NOT NULL DEFAULT '',
                duration_seconds REAL NOT NULL DEFAULT 0,
                model_execution_seconds REAL NOT NULL DEFAULT 0,
                tool_execution_seconds REAL NOT NULL DEFAULT 0,
                model TEXT NOT NULL DEFAULT '',
                git_branch TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                user_message_count INTEGER NOT NULL DEFAULT 0,
                assistant_message_count INTEGER NOT NULL DEFAULT 0,
                tool_call_count INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                fresh_input_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                failed_tool_count INTEGER NOT NULL DEFAULT 0,
                subagent_instance_count INTEGER NOT NULL DEFAULT 0,
                indexed_at REAL NOT NULL DEFAULT 0,
                file_mtime REAL NOT NULL DEFAULT 0,
                file_path TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE session_artifacts (
                session_key TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                path TEXT NOT NULL,
                schema_version TEXT NOT NULL DEFAULT '',
                source_path TEXT NOT NULL DEFAULT '',
                source_mtime REAL NOT NULL DEFAULT 0,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0,
                PRIMARY KEY(session_key, artifact_type)
            );
        """)

        # 确认旧表没有新列
        old_cols = {
            r['name']
            for r in conn.execute('PRAGMA table_info(session_artifacts)').fetchall()
        }
        assert 'content_hash' not in old_cols
        assert 'validation_status' not in old_cols

        # 调用迁移
        ensure_session_artifacts_schema(conn)
        conn.commit()

        # 新列已存在
        new_cols = {
            r['name']
            for r in conn.execute('PRAGMA table_info(session_artifacts)').fetchall()
        }
        assert 'content_hash' in new_cols
        assert 'validation_status' in new_cols

        # 再次调用不报错（幂等）
        ensure_session_artifacts_schema(conn)
        conn.commit()
        conn.close()

    def test_repair_with_session_keys_filter(self, tmp_path):
        """repair_artifact_associations 支持 session_keys 过滤。"""
        conn = _setup_db(tmp_path)
        index_dir = tmp_path
        _insert_session(conn, 'codex', 'filter-1')
        _insert_session(conn, 'codex', 'filter-2')
        p1, s1, h1 = _write_artifact(index_dir, 'codex', 'filter-1')
        p2, s2, h2 = _write_artifact(index_dir, 'codex', 'filter-2')

        # filter-1 正常，filter-2 指向缺失文件
        upsert_session_artifact(
            conn,
            session_key='codex:filter-1',
            artifact_type=_ARTIFACT_TYPE,
            path=str(p1),
            size_bytes=s1,
            content_hash=h1,
            validation_status='ok',
        )
        upsert_session_artifact(
            conn,
            session_key='codex:filter-2',
            artifact_type=_ARTIFACT_TYPE,
            path='/missing.json',
            size_bytes=s2,
        )
        conn.commit()

        # 只 repair filter-1
        stats = repair_artifact_associations(
            conn, session_keys={'codex:filter-1'}
        )
        conn.commit()
        assert stats['repaired'] == 0
        assert stats['removed'] == 0

        # filter-2 行仍然存在（没有被 repair）
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM session_artifacts WHERE session_key = ?',
            ('codex:filter-2',),
        ).fetchone()
        assert row['cnt'] == 1

        # repair filter-2 → 行被删除
        stats2 = repair_artifact_associations(
            conn, session_keys={'codex:filter-2'}
        )
        conn.commit()
        assert stats2['removed'] == 1
        conn.close()
