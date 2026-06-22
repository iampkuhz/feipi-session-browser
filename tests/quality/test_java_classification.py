"""Java/Gradle 文件分类与质量目标路由测试。"""
import pytest
from scripts.claude_hooks.classify import classify_file, required_quality_targets


def test_java_src_main_classification():
    c = classify_file('java/core-domain/src/main/java/com/feipi/session/browser/domain/Foo.java')
    assert c.category == 'java-src'
    assert c.requires_quality_gate
    assert c.quality_target == 'java-src'


def test_java_src_test_classification():
    c = classify_file('java/architecture-tests/src/test/java/com/feipi/BarTest.java')
    assert c.category == 'java-src'
    assert c.quality_target == 'java-src'


def test_java_build_classification():
    assert classify_file('build-logic/src/main/kotlin/feipi.java-base.gradle.kts').quality_target == 'java-build'
    assert classify_file('gradle/libs.versions.toml').quality_target == 'java-build'
    assert classify_file('settings.gradle.kts').quality_target == 'java-build'


def test_java_root_dsl_classification():
    assert classify_file('build.gradle.kts').quality_target == 'java-build'
    assert classify_file('gradle.properties').quality_target == 'java-build'


def test_java_windows_path_normalization():
    c = classify_file('java\\core-domain\\src\\main\\java\\com\\feipi\\Foo.java')
    assert c.quality_target == 'java-src'
    assert c.file == 'java/core-domain/src/main/java/com/feipi/Foo.java'


def test_java_multi_target_dedup():
    targets = required_quality_targets([
        'java/core-domain/src/main/java/com/feipi/A.java',
        'java/app-cli/src/main/java/com/feipi/B.java',
        'build.gradle.kts',
    ])
    assert 'java-src' in targets
    assert 'java-build' in targets
    assert targets.count('java-src') == 1
