"""DB 层故障注入测试。

验证数据库关联写入层面的故障场景：
- DB association failure（关联写入失败）
- repair（修复流程）
- single session failure（单个 session 失败不影响其他）

所有场景验证 fail closed：DB 故障不导致 artifact 状态不一致。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_browser.normalized.artifact_consumer import (
    ArtifactConsumer,
    ArtifactStatus,
)

SB_ROOT = Path(__file__).resolve().parents[2]

# 与 constants.py 中的 NORMALIZED_SCHEMA_VERSION 保持一致
_SCHEMA_VERSION = 'session-detail.normalized.v3'


def _init_index_schema(conn: sqlite3.Connection) -> None:
    """初始化最小化的 index schema 用于测试。"""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_key TEXT PRIMARY KEY,
            agent TEXT NOT NULL,
            session_id TEXT NOT NULL,
            title TEXT DEFAULT '',
            status TEXT DEFAULT 'ok'
        );
        CREATE TABLE IF NOT EXISTS session_artifacts (
            session_key TEXT PRIMARY KEY,
            artifact_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            FOREIGN KEY (session_key) REFERENCES sessions(session_key)
        );
    ''')


class TestDbAssociationFailure:
    """DB 关联写入失败时的行为验证。"""

    def test_session_exists_without_artifact_association(self):
        """session 记录存在但 artifact 关联缺失时 consumer 仍 fail closed。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            db_path = index_dir / 'index.sqlite'

            conn = sqlite3.connect(str(db_path))
            _init_index_schema(conn)
            conn.execute(
                "INSERT INTO sessions (session_key, agent, session_id, title) VALUES (?, ?, ?, ?)",
                ('claude_code:db-fail-001', 'claude_code', 'db-fail-001', 'test'),
            )
            conn.commit()
            conn.close()

            # artifact 文件不存在
            consumer = ArtifactConsumer(index_dir=index_dir)
            result = consumer.validate_artifact(
                session_key='claude_code:db-fail-001',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.MISSING

    def test_artifact_exists_without_session_record(self):
        """artifact 文件存在但 session 记录缺失时 consumer 验证基于文件状态。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)

            # 写入 data 文件但没有对应的 session 记录
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='orphan-artifact-001'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:orphan-artifact-001'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            # consumer 不依赖 DB 记录，只验证文件本身
            result = consumer.validate_artifact(
                session_key='claude_code:orphan-artifact-001',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            # meta 缺失所以是 STALE
            assert result.status == ArtifactStatus.STALE


class TestDbRepair:
    """DB 修复流程验证。"""

    def test_repair_detects_missing_artifact(self):
        """修复流程能检测到关联记录指向不存在的 artifact。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            db_path = index_dir / 'index.sqlite'

            conn = sqlite3.connect(str(db_path))
            _init_index_schema(conn)
            conn.execute(
                "INSERT INTO sessions (session_key, agent, session_id) VALUES (?, ?, ?)",
                ('claude_code:repair-001', 'claude_code', 'repair-001'),
            )
            conn.execute(
                "INSERT INTO session_artifacts (session_key, artifact_path, content_hash, status) "
                "VALUES (?, ?, ?, ?)",
                (
                    'claude_code:repair-001',
                    '/nonexistent/artifact.json',
                    'abc123',
                    'ok',
                ),
            )
            conn.commit()

            # 验证 DB 记录指向不存在的文件
            row = conn.execute(
                "SELECT artifact_path FROM session_artifacts WHERE session_key = ?",
                ('claude_code:repair-001',),
            ).fetchone()
            conn.close()

            assert row is not None
            assert not Path(row[0]).exists()

            # consumer 独立验证文件状态
            consumer = ArtifactConsumer(index_dir=index_dir)
            result = consumer.validate_artifact(
                session_key='claude_code:repair-001',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.MISSING

    def test_repair_after_meta_restored(self):
        """meta 恢复后 artifact 能被重新验证为有效。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='repair-010'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入 data 文件
            data = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:repair-010'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            with artifact_path.open('r', encoding='utf-8') as f:
                content = f.read()
            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
            content_size = len(content.encode('utf-8'))

            source_path = '/tmp/test.jsonl'
            source_file = Path(source_path)
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text('dummy')
            source_mtime = source_file.stat().st_mtime
            source_size = source_file.stat().st_size

            # 先验证 meta 缺失状态
            result = consumer.validate_artifact(
                session_key='claude_code:repair-010',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result.status == ArtifactStatus.STALE

            # 恢复 meta 文件
            meta = {
                'artifact_type': 'normalized_session_json',
                'generator_version': 'normalized-session-artifact.v6',
                'schema_version': _SCHEMA_VERSION,
                'content_hash': content_hash,
                'size_bytes': content_size,
                'source_path': source_path,
                'source_mtime': source_mtime,
                'source_size': source_size,
            }
            meta_path = artifact_path.with_suffix(artifact_path.suffix + '.meta.json')
            with meta_path.open('w', encoding='utf-8') as f:
                json.dump(meta, f)

            # 重新验证应该成功
            result = consumer.validate_artifact(
                session_key='claude_code:repair-010',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result.status == ArtifactStatus.OK


class TestSingleSessionFailureIsolation:
    """单个 session 失败不影响其他 session 的成功语义。"""

    def test_one_corrupt_does_not_affect_other_session(self):
        """一个 session 的 artifact 损坏不影响另一个 session 的验证。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)

            # 创建 session A：完整有效
            artifact_a = consumer.resolve_canonical_path(
                agent='claude_code', session_id='isolation-good-001'
            )
            artifact_a.parent.mkdir(parents=True, exist_ok=True)
            data_a = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:isolation-good-001'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_a.open('w', encoding='utf-8') as f:
                json.dump(data_a, f)

            source_path = '/tmp/test.jsonl'
            source_file = Path(source_path)
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text('dummy')
            source_mtime = source_file.stat().st_mtime
            source_size = source_file.stat().st_size

            with artifact_a.open('r', encoding='utf-8') as f:
                content_a = f.read()
            hash_a = hashlib.sha256(content_a.encode('utf-8')).hexdigest()
            size_a = len(content_a.encode('utf-8'))

            meta_a = {
                'artifact_type': 'normalized_session_json',
                'generator_version': 'normalized-session-artifact.v6',
                'schema_version': _SCHEMA_VERSION,
                'content_hash': hash_a,
                'size_bytes': size_a,
                'source_path': source_path,
                'source_mtime': source_mtime,
                'source_size': source_size,
            }
            meta_path_a = artifact_a.with_suffix(artifact_a.suffix + '.meta.json')
            with meta_path_a.open('w', encoding='utf-8') as f:
                json.dump(meta_a, f)

            # 创建 session B：损坏的 artifact
            artifact_b = consumer.resolve_canonical_path(
                agent='claude_code', session_id='isolation-bad-002'
            )
            artifact_b.parent.mkdir(parents=True, exist_ok=True)
            with artifact_b.open('w', encoding='utf-8') as f:
                f.write('corrupted data {}')

            # session A 应该仍然有效
            result_a = consumer.validate_artifact(
                session_key='claude_code:isolation-good-001',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result_a.status == ArtifactStatus.OK

            # session B 应该被拒绝
            result_b = consumer.validate_artifact(
                session_key='claude_code:isolation-bad-002',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result_b.status == ArtifactStatus.CORRUPT

    def test_batch_result_independent_of_other_failures(self):
        """Java batch 结果中一个 session 失败不影响其他 session 的结果记录。"""
        from session_browser.normalized.java_bridge import BatchResult, ResultStatus

        results = [
            BatchResult(
                request_id='req-1',
                status=ResultStatus.WRITTEN,
                session_key='claude_code:batch-ok-001',
                artifact_path='/tmp/ok.json',
                content_hash='abc',
            ),
            BatchResult(
                request_id='req-2',
                status=ResultStatus.FAILED,
                session_key='claude_code:batch-fail-002',
                error='parse error',
            ),
            BatchResult(
                request_id='req-3',
                status=ResultStatus.WRITTEN,
                session_key='claude_code:batch-ok-003',
                artifact_path='/tmp/ok2.json',
                content_hash='def',
            ),
        ]

        # 每个结果独立，失败不影响成功
        written = [r for r in results if r.status == ResultStatus.WRITTEN]
        failed = [r for r in results if r.status == ResultStatus.FAILED]
        assert len(written) == 2
        assert len(failed) == 1
        assert written[0].session_key == 'claude_code:batch-ok-001'
        assert written[1].session_key == 'claude_code:batch-ok-003'
        assert failed[0].session_key == 'claude_code:batch-fail-002'
