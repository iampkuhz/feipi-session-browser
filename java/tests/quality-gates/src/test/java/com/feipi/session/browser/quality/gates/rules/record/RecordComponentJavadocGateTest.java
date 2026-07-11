package com.feipi.session.browser.quality.gates.rules.record;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.quality.gates.core.QualityGateContext;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** {@link RecordComponentJavadocGate} 使用 fixture 文件的集成测试。 */
class RecordComponentJavadocGateTest {

  private final RecordComponentJavadocGate gate = new RecordComponentJavadocGate();

  private static Path fixturePath(String relative) {
    return Path.of("src/test/resources/fixtures/record-component-javadocs").resolve(relative);
  }

  private QualityGateContext contextFor(Path... paths) {
    return QualityGateContext.builder()
        .repoRoot(Path.of("").toAbsolutePath())
        .inputPaths(List.of(paths))
        .environment(Map.of())
        .build();
  }

  @Test
  void idIsRecordComponentJavadocs() {
    assertThat(gate.id()).isEqualTo("record-component-javadocs");
  }

  @Test
  void validSimpleRecord() throws Exception {
    var violations = gate.check(contextFor(fixturePath("valid/SimpleValidRecord.java")));
    assertThat(violations).isEmpty();
  }

  @Test
  void validGenericRecord() throws Exception {
    var violations = gate.check(contextFor(fixturePath("valid/GenericValidRecord.java")));
    assertThat(violations).isEmpty();
  }

  @Test
  void validAnnotatedRecord() throws Exception {
    var violations = gate.check(contextFor(fixturePath("valid/AnnotatedValidRecord.java")));
    assertThat(violations).isEmpty();
  }

  @Test
  void validNestedRecord() throws Exception {
    var violations = gate.check(contextFor(fixturePath("valid/NestedValidRecord.java")));
    assertThat(violations).isEmpty();
  }

  @Test
  void validImplementsRecord() throws Exception {
    var violations = gate.check(contextFor(fixturePath("valid/ImplementsValidRecord.java")));
    assertThat(violations).isEmpty();
  }

  @Test
  void missingRecordJavadoc() throws Exception {
    var violations = gate.check(contextFor(fixturePath("invalid/MissingRecordJavadoc.java")));
    assertThat(violations).hasSize(1);

    var v = violations.get(0);
    assertThat(v.code()).isEqualTo("RECORD_JAVADOC_MISSING");
    assertThat(v.line()).isGreaterThanOrEqualTo(1);
    assertThat(v.attributes()).containsEntry("record", "MissingRecordJavadoc");
    assertThat(v.message()).contains("缺少类型 Javadoc");
  }

  @Test
  void missingParam() throws Exception {
    var violations = gate.check(contextFor(fixturePath("invalid/MissingParam.java")));
    assertThat(violations).hasSize(1);

    var v = violations.get(0);
    assertThat(v.code()).isEqualTo("RECORD_COMPONENT_PARAM_MISSING");
    assertThat(v.attributes())
        .containsEntry("record", "MissingParam")
        .containsEntry("component", "age");
    assertThat(v.message()).contains("缺少 @param 说明");
  }

  @Test
  void nonChineseParam() throws Exception {
    var violations = gate.check(contextFor(fixturePath("invalid/NonChineseParam.java")));

    assertThat(violations).hasSize(2);
    for (var v : violations) {
      assertThat(v.code()).isEqualTo("RECORD_COMPONENT_PARAM_NOT_CHINESE");
      assertThat(v.message()).contains("必须包含中文");
    }
    assertThat(violations)
        .extracting(v -> v.attributes().get("component"))
        .containsExactlyInAnyOrder("name", "age");
  }

  @Test
  void typeParamOnly() throws Exception {
    var violations = gate.check(contextFor(fixturePath("invalid/TypeParamOnly.java")));

    // @param <T> 不算 component，value 缺少 @param
    assertThat(violations).hasSize(1);
    var v = violations.get(0);
    assertThat(v.code()).isEqualTo("RECORD_COMPONENT_PARAM_MISSING");
    assertThat(v.attributes()).containsEntry("component", "value");
  }

  @Test
  void multipleViolations() throws Exception {
    var violations = gate.check(contextFor(fixturePath("invalid/MultipleViolations.java")));

    // 缺少 Javadoc → RECORD_JAVADOC_MISSING（只报 record 级别）
    assertThat(violations).hasSize(1);
    assertThat(violations.get(0).code()).isEqualTo("RECORD_JAVADOC_MISSING");
  }

  @Test
  void violationsAreSortedByPathAndLine() throws Exception {
    var violations =
        gate.check(
            contextFor(
                fixturePath("invalid/NonChineseParam.java"),
                fixturePath("invalid/MissingParam.java"),
                fixturePath("invalid/MissingRecordJavadoc.java")));

    // 验证排序：path 升序，然后 line 升序
    for (int i = 1; i < violations.size(); i++) {
      var prev = violations.get(i - 1);
      var curr = violations.get(i);
      var pathCmp = prev.path().toString().compareTo(curr.path().toString());
      if (pathCmp == 0) {
        assertThat(prev.line()).isLessThanOrEqualTo(curr.line());
      } else {
        assertThat(pathCmp).isLessThan(0);
      }
    }
  }
}
