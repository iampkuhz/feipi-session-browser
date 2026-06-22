"""Java/Gradle 文件分类与质量目标路由测试。

覆盖 J1-040 新增功能：
- 扩展 java-build 模式（gradlew、lockfile）
- 未知 Java/Gradle 路径 fail closed
- first-match 路由行为
- Windows 路径规范化
- 多文件、多 target 去重
- dominance 去重
- 并行执行元数据
- artifact 元数据字段
- 过期 artifact 检测
"""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.claude_hooks.classify import (
    DOMINANCE,
    classify_file,
    effective_targets,
    required_quality_targets,
)
from scripts.quality.quality_artifact import (
    PASS,
    GateDetail,
    QualitySummary,
    is_artifact_fresh,
    resolve_base_commit,
    resolve_dirty_hash,
    utc_now,
)
from scripts.quality.quality_targets import (
    TARGET_DOMINANCE,
    TARGET_META,
    applicable_gates_for_target,
    required_gates_for_target,
    target_parallel_meta,
)


# 01. 基本分类测试
class TestJavaBasicClassification:
    """Java 源文件和构建文件基本分类。"""

    @pytest.mark.contract_case('J1-040-001')
    def test_java_src_main_classification(self):
        c = classify_file('java/core-domain/src/main/java/com/feipi/session/browser/domain/Foo.java')
        assert c.category == 'java-src'
        assert c.requires_quality_gate
        assert c.quality_target == 'java-src'
        assert c.allowed_by_default is True

    @pytest.mark.contract_case('J1-040-001')
    def test_java_src_test_classification(self):
        c = classify_file('java/architecture-tests/src/test/java/com/feipi/BarTest.java')
        assert c.category == 'java-src'
        assert c.quality_target == 'java-src'

    @pytest.mark.contract_case('J1-040-001')
    def test_java_build_classification(self):
        assert classify_file('build-logic/src/main/kotlin/feipi.java-base.gradle.kts').quality_target == 'java-build'
        assert classify_file('gradle/libs.versions.toml').quality_target == 'java-build'
        assert classify_file('settings.gradle.kts').quality_target == 'java-build'

    @pytest.mark.contract_case('J1-040-001')
    def test_java_root_dsl_classification(self):
        assert classify_file('build.gradle.kts').quality_target == 'java-build'
        assert classify_file('gradle.properties').quality_target == 'java-build'


# 02. 扩展模式测试
class TestJavaExpandedPatterns:
    """J1-040 新增的 gradlew、lockfile 等模式。"""

    @pytest.mark.contract_case('J1-040-002')
    def test_gradlew_classification(self):
        c = classify_file('gradlew')
        assert c.category == 'java-build'
        assert c.quality_target == 'java-build'
        assert c.requires_quality_gate is True

    @pytest.mark.contract_case('J1-040-002')
    def test_gradlew_bat_classification(self):
        c = classify_file('gradlew.bat')
        assert c.category == 'java-build'
        assert c.quality_target == 'java-build'
        assert c.requires_quality_gate is True

    @pytest.mark.contract_case('J1-040-002')
    def test_lockfile_classification(self):
        c = classify_file('settings-gradle.lockfile')
        assert c.category == 'java-build'
        assert c.quality_target == 'java-build'
        assert c.requires_quality_gate is True

    @pytest.mark.contract_case('J1-040-002')
    def test_gradle_wrapper_jar(self):
        c = classify_file('gradle/wrapper/gradle-wrapper.jar')
        assert c.quality_target == 'java-build'

    @pytest.mark.contract_case('J1-040-002')
    def test_gradle_verification_metadata(self):
        c = classify_file('gradle/verification-metadata.xml')
        assert c.quality_target == 'java-build'


# 03. Fail-closed 测试
class TestJavaFailClosed:
    """未知 Java/Gradle 路径必须 fail closed。"""

    @pytest.mark.contract_case('J1-040-003')
    def test_unknown_java_file_fails_closed(self):
        c = classify_file('some/random/file.java')
        assert c.category == 'java-src-unknown'
        assert c.quality_target == 'java-src'
        assert c.requires_quality_gate is True
        assert c.allowed_by_default is False

    @pytest.mark.contract_case('J1-040-003')
    def test_unknown_gradle_file_fails_closed(self):
        c = classify_file('random.gradle.kts')
        assert c.category == 'java-build-unknown'
        assert c.quality_target == 'java-build'
        assert c.requires_quality_gate is True
        assert c.allowed_by_default is False

    @pytest.mark.contract_case('J1-040-003')
    def test_first_match_known_java_not_unknown(self):
        """已知模式的 Java 文件应匹配 java-src，而非 java-src-unknown。"""
        c = classify_file('java/core-domain/src/main/java/com/feipi/Foo.java')
        assert c.category == 'java-src'
        assert c.allowed_by_default is True

    @pytest.mark.contract_case('J1-040-003')
    def test_first_match_known_build_not_unknown(self):
        """已知模式的构建文件应匹配 java-build，而非 java-build-unknown。"""
        c = classify_file('build.gradle.kts')
        assert c.category == 'java-root-dsl'
        assert c.allowed_by_default is True


# 04. Windows 路径测试
class TestJavaWindowsPaths:
    """Windows 风格路径的规范化。"""

    @pytest.mark.contract_case('J1-040-004')
    def test_java_windows_path_normalization(self):
        c = classify_file('java\\core-domain\\src\\main\\java\\com\\feipi\\Foo.java')
        assert c.quality_target == 'java-src'
        assert c.file == 'java/core-domain/src/main/java/com/feipi/Foo.java'

    @pytest.mark.contract_case('J1-040-004')
    def test_gradlew_windows_path(self):
        c = classify_file('.\\gradlew')
        assert c.quality_target == 'java-build'


# 05. 多文件多 target 去重测试
class TestJavaMultiTargetDedup:
    """多文件场景下 target 去重。"""

    @pytest.mark.contract_case('J1-040-005')
    def test_java_multi_target_dedup(self):
        targets = required_quality_targets([
            'java/core-domain/src/main/java/com/feipi/A.java',
            'java/app-cli/src/main/java/com/feipi/B.java',
            'build.gradle.kts',
        ])
        assert 'java-src' in targets
        assert 'java-build' in targets
        assert targets.count('java-src') == 1
        assert targets.count('java-build') == 1

    @pytest.mark.contract_case('J1-040-005')
    def test_multi_file_same_target(self):
        targets = required_quality_targets([
            'java/a/src/main/java/A.java',
            'java/b/src/main/java/B.java',
        ])
        assert targets == ['java-src']


# 06. Dominance 去重测试
class TestJavaDominance:
    """Dominance 声明消除重复 Gradle 基线。"""

    @pytest.mark.contract_case('J1-040-006')
    def test_dominance_removes_java_build(self):
        result = effective_targets(['java-src', 'java-build'])
        assert result == ['java-src']

    @pytest.mark.contract_case('J1-040-006')
    def test_dominance_preserves_standalone_java_build(self):
        result = effective_targets(['java-build'])
        assert result == ['java-build']

    @pytest.mark.contract_case('J1-040-006')
    def test_dominance_preserves_other_targets(self):
        result = effective_targets(['java-src', 'hook-runtime'])
        assert result == ['java-src', 'hook-runtime']

    @pytest.mark.contract_case('J1-040-006')
    def test_dominance_metadata_consistency(self):
        """classify.py 和 quality_targets.py 的 dominance 声明必须一致。"""
        assert DOMINANCE == TARGET_DOMINANCE

    @pytest.mark.contract_case('J1-040-006')
    def test_quality_targets_effective_targets(self):
        from scripts.quality.quality_targets import effective_targets as qt_eff
        result = qt_eff(['java-src', 'java-build', 'harness'])
        assert 'java-build' not in result
        assert 'java-src' in result
        assert 'harness' in result


# 07. 并行元数据测试
class TestParallelMeta:
    """并行执行元数据。"""

    @pytest.mark.contract_case('J1-040-007')
    def test_java_src_parallel_meta(self):
        meta = target_parallel_meta('java-src')
        assert meta['parallel_safe'] is True
        assert 'gradle-daemon' in meta['exclusive_resources']
        assert meta['timeout'] == 600

    @pytest.mark.contract_case('J1-040-007')
    def test_java_build_parallel_meta(self):
        meta = target_parallel_meta('java-build')
        assert 'gradle-daemon' in meta['exclusive_resources']

    @pytest.mark.contract_case('J1-040-007')
    def test_java_targets_share_gradle_daemon(self):
        """java-src 和 java-build 共享 gradle-daemon 互斥资源。"""
        src_res = set(target_parallel_meta('java-src')['exclusive_resources'])
        build_res = set(target_parallel_meta('java-build')['exclusive_resources'])
        assert src_res & build_res == {'gradle-daemon'}

    @pytest.mark.contract_case('J1-040-007')
    def test_unknown_target_default_meta(self):
        meta = target_parallel_meta('nonexistent')
        assert meta['parallel_safe'] is True
        assert meta['exclusive_resources'] == []
        assert meta['timeout'] == 300


# 08. Artifact 元数据测试
class TestArtifactMetadata:
    """QualitySummary 新增 artifact 元数据字段。"""

    @pytest.mark.contract_case('J1-040-008')
    def test_summary_has_run_id(self):
        from scripts.quality.run_quality_gate import build_summary
        started = '2026-01-01T00:00:00Z'
        details = [GateDetail(name='javaCheck', status=PASS, command=['./gradlew', 'check'])]
        summary = build_summary('java-src', 'test-change', started, details)
        assert summary.runId
        assert 'java-src' in summary.runId
        assert 'test-change' in summary.runId

    @pytest.mark.contract_case('J1-040-008')
    def test_summary_has_base_commit(self):
        from scripts.quality.run_quality_gate import build_summary
        started = '2026-01-01T00:00:00Z'
        details = [GateDetail(name='javaCheck', status=PASS, command=['./gradlew', 'check'])]
        summary = build_summary('java-src', 'test-change', started, details, repo_root=Path('.'))
        assert summary.baseCommit
        assert len(summary.baseCommit) >= 7

    @pytest.mark.contract_case('J1-040-008')
    def test_summary_has_generated_at(self):
        from scripts.quality.run_quality_gate import build_summary
        started = '2026-01-01T00:00:00Z'
        details = [GateDetail(name='javaCheck', status=PASS)]
        summary = build_summary('java-src', 'test', started, details)
        assert summary.generatedAt == started

    @pytest.mark.contract_case('J1-040-008')
    def test_summary_has_freshness(self):
        from scripts.quality.run_quality_gate import build_summary
        started = '2026-01-01T00:00:00Z'
        details = [GateDetail(name='javaCheck', status=PASS)]
        summary = build_summary('java-src', 'test', started, details)
        assert summary.freshness == '0s'


# 09. 过期 artifact 检测测试
class TestStaleArtifact:
    """Stop hook 拒绝陈旧证据。"""

    @pytest.mark.contract_case('J1-040-009')
    def test_missing_artifact_not_fresh(self):
        assert is_artifact_fresh('/tmp/nonexistent_quality_artifact.json') is False

    @pytest.mark.contract_case('J1-040-009')
    def test_fresh_artifact_is_fresh(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            f.write(b'{}')
            f.flush()
            assert is_artifact_fresh(f.name, max_age_seconds=60) is True
            Path(f.name).unlink()

    @pytest.mark.contract_case('J1-040-009')
    def test_old_artifact_is_stale(self):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            f.write(b'{}')
            f.flush()
            # 设置文件修改时间为 2 小时前
            old_time = datetime.now(timezone.utc).timestamp() - 7200
            import os
            os.utime(f.name, (old_time, old_time))
            assert is_artifact_fresh(f.name, max_age_seconds=3600) is False
            Path(f.name).unlink()


# 10. Gate pattern 触发测试
class TestJavaGatePatterns:
    """Java target 的 gate 触发模式。"""

    @pytest.mark.contract_case('J1-040-010')
    def test_java_src_gates(self):
        gates = required_gates_for_target('java-src')
        assert 'javaCheck' in gates
        assert 'javaChineseComments' in gates
        assert 'noJavaTestSkips' in gates

    @pytest.mark.contract_case('J1-040-010')
    def test_java_build_gates(self):
        gates = required_gates_for_target('java-build')
        assert 'javaCheck' in gates

    @pytest.mark.contract_case('J1-040-010')
    def test_java_build_trigger_for_gradlew(self):
        gates = applicable_gates_for_target('java-build', ['gradlew'])
        assert 'javaCheck' in gates

    @pytest.mark.contract_case('J1-040-010')
    def test_java_build_trigger_for_lockfile(self):
        gates = applicable_gates_for_target('java-build', ['settings-gradle.lockfile'])
        assert 'javaCheck' in gates

    @pytest.mark.contract_case('J1-040-010')
    def test_java_src_trigger_for_unknown_java(self):
        """未知 Java 文件也应触发 java-src 的 gate。"""
        gates = applicable_gates_for_target('java-src', ['some/random/File.java'])
        assert 'javaCheck' in gates


# 11. 并行失败确定性测试
class TestParallelFailureDeterminism:
    """并行 target 结果顺序确定，失败返回非零。"""

    @pytest.mark.contract_case('J1-040-011')
    def test_effective_targets_preserves_order(self):
        result = effective_targets(['harness', 'java-src', 'java-build', 'hook-runtime'])
        assert result == ['harness', 'java-src', 'hook-runtime']

    @pytest.mark.contract_case('J1-040-011')
    def test_required_targets_deterministic_order(self):
        files = [
            'build.gradle.kts',
            'java/core-domain/src/main/java/com/feipi/Foo.java',
            '.claude/hooks/stop.sh',
        ]
        targets1 = required_quality_targets(files)
        targets2 = required_quality_targets(files)
        assert targets1 == targets2
