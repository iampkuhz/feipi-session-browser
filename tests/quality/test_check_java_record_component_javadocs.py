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
    """每个 component 都有中文 @param 时通过。"""
    path = _write(
        tmp_path,
        '''
package demo;

/** 查询结果行。
 *
 * @param projectCount 当前过滤条件下的项目数量。
 * @param sessionCount 当前过滤条件下的 session 数量。
 */
public record Sample(long projectCount, long sessionCount) {}
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
public record Sample(long projectCount, long sessionCount) {}
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
public record Sample(long projectCount) {}
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

    assert [v.code for v in violations] == ['RECORD_JAVADOC_MISSING']


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
    @Deprecated List<T> names,
    String[] tags,
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
record Sample(String requestId, String rootPath) {}
''',
    )

    assert checker.check_file(path) == []
