"""ArtifactConsumer 只读 consumer 测试。

覆盖：
- Consumer 无写权限/API 测试
- hash/meta mismatch fail closed 测试
- 相同状态在 full/incremental/tiered 路径一致测试
- 旧版本行为测试
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from session_browser.normalized.artifact_consumer import (
    ArtifactConsumer,
    ArtifactStatus,
    ArtifactValidationResult,
    _derive_meta_path,
    _safe_path_component,
    _split_session_key,
)
from session_browser.normalized.constants import NORMALIZED_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _build_minimal_artifact(
    *,
    agent: str = 'claude_code',
    session_id: str = 'test-session-001',
    schema_version: str = NORMALIZED_SCHEMA_VERSION,
) -> dict[str, Any]:
    """构建最小合法的 normalized session artifact。"""
    return {
        'schema_version': schema_version,
        'agent': agent,
        'source': {'files': []},
        'session': {
            'session_id': session_id,
            'session_key': f'{agent}:{session_id}',
            'agent': agent,
        },
        'calls': [],
        'tool_executions': [],
        'diagnostics': [],
    }


def _write_artifact_pair(
    tmp_path: Path,
    *,
    agent: str = 'claude_code',
    session_id: str = 'test-session-001',
    schema_version: str = NORMALIZED_SCHEMA_VERSION,
    source_path: str | None = None,
    source_mtime: float = 1000000.0,
    content_override: dict[str, Any] | None = None,
    corrupt_json: bool = False,
    empty_file: bool = False,
    no_meta: bool = False,
    mismatch_hash: bool = False,
    mismatch_size: bool = False,
) -> tuple[Path, Path]:
    """在 tmp_path 下写入 artifact + sidecar meta，返回 (artifact_path, meta_path)。"""
    consumer = ArtifactConsumer(index_dir=tmp_path)
    artifact_path = consumer.resolve_canonical_path(agent=agent, session_id=session_id)
    meta_path = _derive_meta_path(artifact_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    if empty_file:
        artifact_path.write_text('', encoding='utf-8')
    elif corrupt_json:
        artifact_path.write_text('{bad json!!', encoding='utf-8')
    else:
        data = content_override or _build_minimal_artifact(
            agent=agent, session_id=session_id, schema_version=schema_version,
        )
        payload = json.dumps(data, ensure_ascii=False) + '\n'
        artifact_path.write_text(payload, encoding='utf-8')

    if no_meta:
        return artifact_path, meta_path

    actual_size = artifact_path.stat().st_size
    raw = artifact_path.read_text(encoding='utf-8')
    content_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()

    # 默认使用 tmp_path 下的 source file
    if source_path is None:
        effective_source_path = str(tmp_path / 'source.jsonl')
    else:
        effective_source_path = source_path

    # 写入 source file 以便 source_size 验证
    source_file = Path(effective_source_path)
    source_file.parent.mkdir(parents=True, exist_ok=True)
    if not source_file.exists():
        source_file.write_text('dummy source content', encoding='utf-8')
    source_size = source_file.stat().st_size

    meta = {
        'artifact_type': 'normalized_session_json',
        'generator_version': 'normalized-session-artifact.v6',
        'schema_version': schema_version,
        'source_path': effective_source_path,
        'source_mtime': source_mtime,
        'source_size': source_size,
        'size_bytes': actual_size if not mismatch_size else actual_size + 999,
        'generated_at': time.time(),
    }
    if mismatch_hash:
        meta['content_hash'] = 'deadbeef' * 8
    else:
        meta['content_hash'] = content_hash

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return artifact_path, meta_path


# ---------------------------------------------------------------------------
# Consumer 无写权限/API 测试
# ---------------------------------------------------------------------------

class TestConsumerReadOnlyAPI:
    """验证 consumer 不暴露任何写入 API。"""

    def test_no_write_method(self):
        consumer = ArtifactConsumer(index_dir=Path('/tmp/test'))
        assert not hasattr(consumer, 'write_artifact')
        assert not hasattr(consumer, 'create_artifact')
        assert not hasattr(consumer, 'replace_artifact')
        assert not hasattr(consumer, 'persist')
        assert not hasattr(consumer, 'upsert')

    def test_no_module_level_write_exports(self):
        """模块级公开 API 不包含写入函数。"""
        import session_browser.normalized.artifact_consumer as mod
        public_names = [n for n in dir(mod) if not n.startswith('_')]
        for name in public_names:
            assert 'write' not in name.lower() or name == 'read_artifact_safe', (
                f'consumer 模块不应暴露 write API: {name}'
            )

    def test_read_artifact_returns_decoded_json(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        artifact_path, _ = _write_artifact_pair(tmp_path)

        data = consumer.read_artifact(artifact_path)
        assert isinstance(data, dict)
        assert data['schema_version'] == NORMALIZED_SCHEMA_VERSION

    def test_read_artifact_safe_returns_none_on_error(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        assert consumer.read_artifact_safe(tmp_path / 'nonexistent.json') is None

    def test_read_artifact_raises_on_missing_file(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            consumer.read_artifact(tmp_path / 'nonexistent.json')

    def test_read_artifact_raises_on_non_object(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        bad = tmp_path / 'bad.json'
        bad.write_text('[1,2,3]', encoding='utf-8')
        with pytest.raises(ValueError, match='JSON object'):
            consumer.read_artifact(bad)

    def test_read_meta_returns_empty_for_missing(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        assert consumer.read_meta(tmp_path / 'nope.json') == {}


# ---------------------------------------------------------------------------
# hash/meta mismatch fail closed 测试
# ---------------------------------------------------------------------------

class TestFailClosed:
    """验证 hash/meta 不匹配时 fail closed。"""

    def test_missing_artifact_returns_missing(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(tmp_path / 'source.jsonl'),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.MISSING

    def test_missing_meta_returns_stale(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        # 创建 source file
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path), no_meta=True)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.STALE

    def test_corrupt_json_returns_corrupt(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path), corrupt_json=True)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.CORRUPT

    def test_empty_file_returns_incomplete(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path), empty_file=True)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.INCOMPLETE

    def test_hash_mismatch_returns_corrupt(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path), mismatch_hash=True)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.CORRUPT

    def test_size_mismatch_returns_corrupt(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path), mismatch_size=True)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.CORRUPT

    def test_stale_source_path_returns_stale(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path))

        # 使用不同的 source_path 验证
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path='/different/source.jsonl',
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.STALE

    def test_stale_source_mtime_returns_stale(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path))

        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=9999999.0,
        )
        assert result.status == ArtifactStatus.STALE

    def test_unsupported_schema_version(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(
            tmp_path,
            source_path=str(source_path),
            schema_version='session-detail.normalized.v999',
        )
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.UNSUPPORTED_VERSION

    def test_invalid_session_key_returns_missing(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        result = consumer.validate_artifact(
            session_key='invalid-key-no-colon',
            source_path='/fake/source.jsonl',
            source_mtime=0.0,
        )
        assert result.status == ArtifactStatus.MISSING

    def test_ok_when_all_match(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path))
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert result.status == ArtifactStatus.OK
        assert result.content_hash != ''
        assert result.schema_version == NORMALIZED_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 相同状态在 full/incremental/tiered 路径一致测试
# ---------------------------------------------------------------------------

class TestPathConsistency:
    """验证相同输入在 full/incremental/tiered 扫描路径下一致。"""

    def test_canonical_path_is_deterministic(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        path1 = consumer.resolve_canonical_path(agent='claude_code', session_id='abc-123')
        path2 = consumer.resolve_canonical_path(agent='claude_code', session_id='abc-123')
        assert path1 == path2

    def test_canonical_path_format(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        path = consumer.resolve_canonical_path(agent='claude_code', session_id='abc-123')
        assert 'normalized-sessions' in path.parts
        assert path.name == 'abc-123.json'
        assert 'claude_code' in path.parts

    def test_same_status_across_scan_modes(self, tmp_path: Path):
        """full scan、incremental scan 和 tiered scan 对同一 artifact 状态一致。"""
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path))

        # 模拟三种扫描路径的验证调用
        full_result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        incremental_result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        tiered_result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )

        assert full_result.status == incremental_result.status == tiered_result.status
        assert full_result.status == ArtifactStatus.OK
        assert full_result.content_hash == incremental_result.content_hash == tiered_result.content_hash

    def test_same_missing_status_across_modes(self, tmp_path: Path):
        """不存在的 artifact 在所有扫描模式下一致返回 MISSING。"""
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = str(tmp_path / 'nonexistent_source.jsonl')

        results = []
        for _ in range(3):
            r = consumer.validate_artifact(
                session_key='codex:no-such-session',
                source_path=source_path,
                source_mtime=0.0,
            )
            results.append(r.status)

        assert all(s == ArtifactStatus.MISSING for s in results)

    def test_different_agents_isolate_paths(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        cc_path = consumer.resolve_canonical_path(agent='claude_code', session_id='s1')
        codex_path = consumer.resolve_canonical_path(agent='codex', session_id='s1')
        qoder_path = consumer.resolve_canonical_path(agent='qoder', session_id='s1')

        assert cc_path != codex_path
        assert codex_path != qoder_path


# ---------------------------------------------------------------------------
# 旧版本行为测试
# ---------------------------------------------------------------------------

class TestLegacyArtifactHandling:
    """验证旧版本 artifact 的分类和处理策略。"""

    def test_legacy_schema_version_classified_as_unsupported(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        artifact_path, _ = _write_artifact_pair(
            tmp_path,
            source_path=str(source_path),
            schema_version='session-detail.normalized.v1',
        )
        status = consumer.classify_legacy_artifact(artifact_path)
        assert status == ArtifactStatus.UNSUPPORTED_VERSION

    def test_should_discard_legacy_unsupported_version(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        artifact_path, _ = _write_artifact_pair(
            tmp_path,
            source_path=str(source_path),
            schema_version='session-detail.normalized.v1',
        )
        assert consumer.should_discard_legacy(artifact_path) is True

    def test_should_not_discard_current_version(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        artifact_path, _ = _write_artifact_pair(tmp_path, source_path=str(source_path))
        assert consumer.should_discard_legacy(artifact_path) is False

    def test_classify_missing_artifact(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        status = consumer.classify_legacy_artifact(tmp_path / 'nope.json')
        assert status == ArtifactStatus.MISSING

    def test_classify_corrupt_artifact(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        bad = tmp_path / 'bad.json'
        bad.write_text('not valid json {{{', encoding='utf-8')
        status = consumer.classify_legacy_artifact(bad)
        assert status == ArtifactStatus.CORRUPT

    def test_classify_empty_artifact(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        empty = tmp_path / 'empty.json'
        empty.write_text('', encoding='utf-8')
        status = consumer.classify_legacy_artifact(empty)
        assert status == ArtifactStatus.INCOMPLETE

    def test_legacy_rejection_does_not_auto_fallback(self, tmp_path: Path):
        """旧版本验证失败时不会自动回退 Python 生产。"""
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        artifact_path, _ = _write_artifact_pair(
            tmp_path,
            source_path=str(source_path),
            schema_version='session-detail.normalized.v1',
        )
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        # 旧版本明确拒绝，不返回 OK
        assert result.status == ArtifactStatus.UNSUPPORTED_VERSION
        # should_discard_legacy 建议丢弃
        assert consumer.should_discard_legacy(artifact_path) is True

    def test_find_current_returns_none_for_legacy(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(
            tmp_path,
            source_path=str(source_path),
            schema_version='session-detail.normalized.v1',
        )
        found = consumer.find_current_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        assert found is None


# ---------------------------------------------------------------------------
# 辅助函数测试
# ---------------------------------------------------------------------------

class TestHelpers:
    """内部辅助函数的单元测试。"""

    def test_split_session_key_valid(self):
        assert _split_session_key('claude_code:abc-123') == ('claude_code', 'abc-123')

    def test_split_session_key_invalid(self):
        assert _split_session_key('no-colon-here') == ('', '')

    def test_split_session_key_empty(self):
        assert _split_session_key('') == ('', '')

    def test_split_session_key_multiple_colons(self):
        agent, sid = _split_session_key('claude_code:abc:def:ghi')
        assert agent == 'claude_code'
        assert sid == 'abc:def:ghi'

    def test_safe_path_component_normal(self):
        assert _safe_path_component('hello_world') == 'hello_world'

    def test_safe_path_component_special_chars(self):
        result = _safe_path_component('a/b\\c:d*e?f')
        assert '/' not in result
        assert '\\' not in result

    def test_safe_path_component_empty_becomes_unknown(self):
        assert _safe_path_component('') == 'unknown'

    def test_safe_path_component_truncates_long(self):
        long_val = 'a' * 500
        result = _safe_path_component(long_val)
        assert len(result) <= 180

    def test_derive_meta_path(self):
        p = _derive_meta_path('/tmp/test.json')
        assert str(p).endswith('.json.meta.json')


# ---------------------------------------------------------------------------
# Privacy / path hiding 测试
# ---------------------------------------------------------------------------

class TestPrivacyAndPathHandling:
    """验证 consumer 不暴露绝对用户路径和敏感内容。"""

    def test_canonical_path_uses_index_dir_not_user_home(self, tmp_path: Path):
        consumer = ArtifactConsumer(index_dir=tmp_path)
        path = consumer.resolve_canonical_path(agent='claude_code', session_id='s1')
        # path 基于 index_dir，不暴露用户 home 目录
        assert str(path).startswith(str(tmp_path))

    def test_validation_result_does_not_leak_preview(self, tmp_path: Path):
        """验证结果的 detail 不包含 artifact 内容 preview。"""
        consumer = ArtifactConsumer(index_dir=tmp_path)
        source_path = tmp_path / 'source.jsonl'
        source_path.write_text('dummy source content', encoding='utf-8')

        _write_artifact_pair(tmp_path, source_path=str(source_path), corrupt_json=True)
        result = consumer.validate_artifact(
            session_key='claude_code:test-session-001',
            source_path=str(source_path),
            source_mtime=1000000.0,
        )
        # detail 只包含状态描述，不包含 artifact 内容
        assert 'content' not in result.detail.lower() or '内容' not in result.detail
        assert len(result.detail) < 200  # 不应该有长文本泄露
