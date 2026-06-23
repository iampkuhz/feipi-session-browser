"""文件层故障注入测试。

验证 artifact 文件写入过程中的故障场景：
- JSON 前退出（写入中断，data 文件不完整）
- JSON 后 meta 前退出（data 存在但 meta 缺失）
- hash mismatch（内容损坏）

所有场景必须 fail closed：consumer 不将中间状态视为有效 artifact。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from session_browser.normalized.artifact_consumer import (
    ArtifactConsumer,
    ArtifactStatus,
)

SB_ROOT = Path(__file__).resolve().parents[2]

# 与 Java 端 ArtifactConstants 及 constants.py 保持一致
_SCHEMA_VERSION = 'session-detail.normalized.v3'


class TestExitBeforeJsonWritten:
    """JSON 数据文件写入前退出：data 文件不存在或不完整。"""

    def test_missing_data_file_is_rejected(self):
        """data 文件缺失时 consumer 返回 MISSING 状态。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-001'
            )
            # 确保文件不存在
            assert not artifact_path.exists()

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-001',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.MISSING

    def test_empty_data_file_is_rejected(self):
        """data 文件存在但内容为空时 consumer 返回 INCOMPLETE。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-002'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            # 创建空 data 文件（模拟写入中断）
            artifact_path.touch()

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-002',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.INCOMPLETE

    def test_truncated_json_data_file_is_rejected(self):
        """data 文件包含截断 JSON 时 consumer 返回 CORRUPT。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-003'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            # 写入截断的 JSON（模拟写入中断）
            with artifact_path.open('w', encoding='utf-8') as f:
                f.write('{"schema_version":"normalized-session-artifact.v6","agen')

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-003',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.CORRUPT


class TestExitAfterJsonBeforeMeta:
    """JSON 数据写入完成但 meta 写入前退出：data 存在但 meta 缺失。"""

    def test_data_without_meta_is_rejected(self):
        """data 文件完整但 meta 缺失时 consumer 不视为有效。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-010'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入完整的 data 文件
            data = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:fault-test-010'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            # 不创建 meta 文件
            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-010',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.STALE
            assert 'meta' in result.detail.lower()

    def test_data_with_empty_meta_is_rejected(self):
        """data 文件完整但 meta 为空文件时 consumer 不视为有效。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-011'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入完整的 data 文件
            data = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:fault-test-011'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            # 创建空的 meta 文件
            meta_path = artifact_path.with_suffix(artifact_path.suffix + '.meta.json')
            meta_path.touch()

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-011',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.STALE


class TestHashMismatch:
    """内容损坏：data 文件内容与 meta 中记录的 hash 不匹配。"""

    def test_corrupted_data_hash_mismatch(self):
        """data 文件内容被修改后 hash 不匹配，consumer 返回 CORRUPT。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-020'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入 data 文件
            data = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:fault-test-020'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            # 计算原始 hash
            with artifact_path.open('r', encoding='utf-8') as f:
                original_content = f.read()
            original_hash = hashlib.sha256(original_content.encode('utf-8')).hexdigest()
            original_size = len(original_content.encode('utf-8'))

            # 写入匹配的 meta
            source_path = '/tmp/test.jsonl'
            source_file = Path(source_path)
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text('dummy')
            source_mtime = source_file.stat().st_mtime
            source_size = source_file.stat().st_size

            meta = {
                'artifact_type': 'normalized_session_json',
                'generator_version': 'normalized-session-artifact.v6',
                'schema_version': _SCHEMA_VERSION,
                'content_hash': original_hash,
                'size_bytes': original_size,
                'source_path': source_path,
                'source_mtime': source_mtime,
                'source_size': source_size,
            }
            meta_path = artifact_path.with_suffix(artifact_path.suffix + '.meta.json')
            with meta_path.open('w', encoding='utf-8') as f:
                json.dump(meta, f)

            # 先验证正常状态
            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-020',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result.status == ArtifactStatus.OK

            # 修改 data 文件内容（模拟损坏），保持 schema_version 正确以测试 hash 校验
            with artifact_path.open('w', encoding='utf-8') as f:
                f.write('{"schema_version":"' + _SCHEMA_VERSION + '","corrupted":true}')

            # 再次验证，应该检测到损坏（size 或 hash 不匹配）
            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-020',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result.status == ArtifactStatus.CORRUPT
            assert 'hash' in result.detail.lower() or 'size' in result.detail.lower()

    def test_size_mismatch_detected(self):
        """meta 记录的 size 与实际文件不同时 consumer 返回 CORRUPT。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-021'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'schema_version': _SCHEMA_VERSION,
                'agent': 'claude_code',
                'calls': [],
                'session': {'session_key': 'claude_code:fault-test-021'},
                'diagnostics': [],
                'source_files': [],
                'token_breakdown': {},
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            source_path = '/tmp/test.jsonl'
            source_file = Path(source_path)
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text('dummy')
            source_mtime = source_file.stat().st_mtime
            source_size = source_file.stat().st_size

            # meta 中记录错误的 size
            meta = {
                'artifact_type': 'normalized_session_json',
                'generator_version': 'normalized-session-artifact.v6',
                'schema_version': _SCHEMA_VERSION,
                'content_hash': 'placeholder',
                'size_bytes': 999999,
                'source_path': source_path,
                'source_mtime': source_mtime,
                'source_size': source_size,
            }
            meta_path = artifact_path.with_suffix(artifact_path.suffix + '.meta.json')
            with meta_path.open('w', encoding='utf-8') as f:
                json.dump(meta, f)

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-021',
                source_path=source_path,
                source_mtime=source_mtime,
            )
            assert result.status == ArtifactStatus.CORRUPT
            assert 'size' in result.detail.lower()


class TestPartialFileNotRecognizedAsValid:
    """部分文件不会被识别为 valid artifact。"""

    def test_meta_without_data_is_stale(self):
        """只有 meta 没有 data 时 consumer 返回 MISSING。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-030'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # 只创建 meta 文件，不创建 data 文件
            meta_path = artifact_path.with_suffix(artifact_path.suffix + '.meta.json')
            meta = {
                'artifact_type': 'normalized_session_json',
                'generator_version': 'normalized-session-artifact.v6',
                'schema_version': _SCHEMA_VERSION,
                'content_hash': 'abc',
                'size_bytes': 100,
            }
            with meta_path.open('w', encoding='utf-8') as f:
                json.dump(meta, f)

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-030',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.MISSING

    def test_unsupported_schema_version_rejected(self):
        """不支持的 schema version 被拒绝。"""
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            consumer = ArtifactConsumer(index_dir=index_dir)
            artifact_path = consumer.resolve_canonical_path(
                agent='claude_code', session_id='fault-test-031'
            )
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入不支持版本的 data 文件
            data = {
                'schema_version': 'future-version-99.0',
                'agent': 'claude_code',
            }
            with artifact_path.open('w', encoding='utf-8') as f:
                json.dump(data, f)

            result = consumer.validate_artifact(
                session_key='claude_code:fault-test-031',
                source_path='/tmp/test.jsonl',
                source_mtime=1000.0,
            )
            assert result.status == ArtifactStatus.UNSUPPORTED_VERSION
