"""测试 Java record component 中文 Javadoc 门禁。"""

from pathlib import Path

from scripts.quality import check_java_record_component_javadocs as checker


def _write(tmp_path: Path, source: str) -> Path:
    """参数：
        tmp_path: pytest 临时目录。
        source: Java 源码内容。

    返回：
        写入后的 Java 文件路径。
    """
    path = tmp_path / 'Sample.java'
    path.write_text(source, encoding='utf-8')
    return path


def test_record_component_chinese_params_pass(tmp_path: Path):
    """每个 component 都有中文 @param 且 component 附近有 Javadoc 时通过。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 当前过滤条件下的项目数量。
 * @param sessionCount 当前过滤条件下的 session 数量。
 */
public record Sample(
    /** 项目数。 */
    long projectCount,

    /** session 数。 */
    long sessionCount) {}
''',
    )

    assert checker.check_file(path) == []


def test_missing_component_param_fails(tmp_path: Path):
    """缺少 component 对应 @param 时失败。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 当前过滤条件下的项目数量。
 */
public record Sample(
    /** 项目数。 */
    long projectCount,

    /** session 数。 */
    long sessionCount) {}
''',
    )

    violations = checker.check_file(path)

    assert [v.code for v in violations] == ['RECORD_COMPONENT_PARAM_MISSING']
    assert 'sessionCount' in violations[0].message


def test_english_component_param_fails(tmp_path: Path):
    """component @param 只有英文说明时失败。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** Query result row.
 *
 * @param projectCount Count of projects.
 */
public record Sample(
    /** 项目数。 */
    long projectCount) {}
''',
    )

    violations = checker.check_file(path)

    assert [v.code for v in violations] == ['RECORD_COMPONENT_PARAM_NOT_CHINESE']
    assert 'projectCount' in violations[0].message


def test_missing_record_javadoc_fails(tmp_path: Path):
    """record 类型本身缺少 Javadoc 时失败。"""
    path = _write(
        tmp_path,
        '''
package demo;

public record Sample(long projectCount) {}
''',
    )

    violations = checker.check_file(path)

    assert 'RECORD_JAVADOC_MISSING' in [v.code for v in violations]


def test_multiline_generic_annotated_components_pass(tmp_path: Path):
    """泛型、注解、数组和 varargs component 能被正确解析。"""
    path = _write(
        tmp_path,
        '''
package demo;

import java.util.List;

/** 复杂 record 示例。
 *
 * @param names 多个名称列表。
 * @param tags 标签数组。
 * @param rest 剩余参数。
 */
public record Sample<T>(
    /** 名称列表。 */
    @Deprecated
    List<T> names,

    /** 标签数组。 */
    String[] tags,

    /** 剩余参数。 */
    String... rest) {}
''',
    )

    assert checker.check_file(path) == []


def test_type_annotation_between_javadoc_and_record_passes(tmp_path: Path):
    """类型注解位于 Javadoc 与 record 之间时仍绑定到 record。"""
    path = _write(
        tmp_path,
        '''
package demo;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/** 批量输入记录。
 *
 * @param requestId 请求标识。
 * @param rootPath 根目录路径。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
record Sample(
    /** 请求标识。 */
    String requestId,

    /** 根目录路径。 */
    String rootPath) {}
''',
    )

    assert checker.check_file(path) == []


def test_component_inline_javadoc_is_not_required(tmp_path: Path):
    """record 级 @param 已说明 component 时不强制 header 内 inline 注释。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 项目数量。
 */
public record Sample(
    long projectCount) {}
''',
    )

    assert checker.check_file(path) == []


def test_quality_changed_files_filters_main_java_paths(tmp_path: Path, monkeypatch):
    """QUALITY_CHANGED_FILES 存在时只检查本轮变更的 main Java 文件。"""
    changed = tmp_path / 'java' / 'demo' / 'src' / 'main' / 'java' / 'demo' / 'Changed.java'
    unchanged = tmp_path / 'java' / 'demo' / 'src' / 'main' / 'java' / 'demo' / 'Unchanged.java'
    changed.parent.mkdir(parents=True)
    changed.write_text(
        '''
package demo;

/** 变更记录。
 *
 * @param value 变更值。
 */
public record Changed(
    /** 变更值。 */
    String value) {}
''',
        encoding='utf-8',
    )
    unchanged.write_text(
        '''
package demo;

public record Unchanged(String value) {}
''',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        'QUALITY_CHANGED_FILES',
        '["java/demo/src/main/java/demo/Changed.java"]',
    )

    paths = checker.discover(['java'])
    filtered = checker._filter_changed_files(
        paths,
        checker._quality_changed_java_files(tmp_path),
        tmp_path.resolve(),
    )

    assert [path.name for path in filtered] == ['Changed.java']
    assert checker.main() == 0


def test_inline_javadoc_language_is_not_checked(tmp_path: Path):
    """header 内 inline 注释不再作为 record component 说明的 required gate。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 项目数量。
 */
public record Sample(
    /** Project count. */
    long projectCount) {}
''',
    )

    assert checker.check_file(path) == []


def test_annotation_same_line_is_not_record_doc_failure(tmp_path: Path):
    """注解换行属于 formatter 责任，不作为 record component 文档 gate。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 项目数量。
 */
public record Sample(
    /** 项目数量。 */
    @Deprecated long projectCount) {}
''',
    )

    assert checker.check_file(path) == []


def test_annotation_own_line_passes(tmp_path: Path):
    """注解单独占行时通过。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 项目数量。
 */
public record Sample(
    /** 项目数量。 */
    @Deprecated
    long projectCount) {}
''',
    )

    assert checker.check_file(path) == []


def test_empty_record_no_component_violations(tmp_path: Path):
    """无 component 的 record 不报 component 相关违规。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 空记录。 */
public record EmptyRecord() {}
''',
    )

    violations = checker.check_file(path)

    assert not any('COMPONENT' in v.code for v in violations)
