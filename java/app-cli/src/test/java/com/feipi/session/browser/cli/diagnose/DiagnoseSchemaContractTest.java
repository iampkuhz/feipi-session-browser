package com.feipi.session.browser.cli.diagnose;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** JSON schema 与字段稳定性契约测试。 */
@DisplayName("diagnose JSON schema 契约测试")
class DiagnoseSchemaContractTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  @DisplayName("schemaVersion 稳定为 diagnose-session.v1")
  void schemaVersionStable() {
    assertThat(DiagnoseOutputModel.SCHEMA_VERSION).isEqualTo("diagnose-session.v1");
  }

  @Test
  @DisplayName("JSON 输出包含全部顶层字段且顺序稳定")
  void jsonTopLevelFieldsComplete() throws Exception {
    DiagnoseOutputModel.DiagnoseOutput output = buildMinimalOutput();
    String json = JsonRenderer.render(output);
    JsonNode root = MAPPER.readTree(json);

    assertThat(root.has("schemaVersion")).isTrue();
    assertThat(root.has("request")).isTrue();
    assertThat(root.has("source")).isTrue();
    assertThat(root.has("raw")).isTrue();
    assertThat(root.has("normalization")).isTrue();
    assertThat(root.has("projection")).isTrue();
    assertThat(root.has("divergence")).isTrue();
    assertThat(root.has("timing")).isTrue();
    assertThat(root.has("warnings")).isTrue();

    // 字段顺序验证（Jackson 默认按声明顺序序列化 record 字段）
    var fieldNames = root.fieldNames();
    List<String> actualOrder = new java.util.ArrayList<>();
    fieldNames.forEachRemaining(actualOrder::add);
    assertThat(actualOrder)
        .containsExactly(
            "schemaVersion",
            "request",
            "source",
            "raw",
            "normalization",
            "projection",
            "divergence",
            "timing",
            "warnings");
  }

  @Test
  @DisplayName("divergence.first 包含必要字段")
  void divergenceFirstFields() throws Exception {
    var divergence =
        new DiagnoseOutputModel.DivergenceInfo(
            "MISMATCH",
            new DiagnoseOutputModel.FirstDivergence(
                "raw→normalization",
                "MISMATCH",
                "expected-desc",
                "observed-desc",
                "evidence-desc",
                "next-desc"));
    var output = outputWithDivergence(divergence);
    String json = JsonRenderer.render(output);
    JsonNode root = MAPPER.readTree(json);
    JsonNode first = root.path("divergence").path("first");

    assertThat(first.has("stage")).isTrue();
    assertThat(first.has("status")).isTrue();
    assertThat(first.has("expected")).isTrue();
    assertThat(first.has("observed")).isTrue();
    assertThat(first.has("evidence")).isTrue();
    assertThat(first.has("nextInspection")).isTrue();
  }

  @Test
  @DisplayName("divergence.first 为 null 时 JSON 输出为 null")
  void divergenceFirstNull() throws Exception {
    var divergence = new DiagnoseOutputModel.DivergenceInfo("MATCH", null);
    var output = outputWithDivergence(divergence);
    String json = JsonRenderer.render(output);
    JsonNode root = MAPPER.readTree(json);
    assertThat(root.path("divergence").path("first").isNull()).isTrue();
  }

  private static DiagnoseOutputModel.DiagnoseOutput buildMinimalOutput() {
    return new DiagnoseOutputModel.DiagnoseOutput(
        DiagnoseOutputModel.SCHEMA_VERSION,
        new DiagnoseOutputModel.RequestInfo("claude_code", "test-session", "/tmp/test"),
        new DiagnoseOutputModel.SourceInfo(
            "UNAVAILABLE", "", 0, "", 0, List.of(), "UNAVAILABLE", Map.of()),
        new DiagnoseOutputModel.RawInfo("UNAVAILABLE", 0, Map.of(), 0, 0, 0, 0, 0, List.of()),
        new DiagnoseOutputModel.NormalizationInfo("UNAVAILABLE", "", 0, 0, 0, 0, 0, 0, 0),
        new DiagnoseOutputModel.ProjectionInfo("UNAVAILABLE", 0, 0, 0, 0, 0),
        new DiagnoseOutputModel.DivergenceInfo("UNAVAILABLE", null),
        new DiagnoseOutputModel.TimingInfo(0, 0, 0, 0, 0),
        List.of());
  }

  private static DiagnoseOutputModel.DiagnoseOutput outputWithDivergence(
      DiagnoseOutputModel.DivergenceInfo divergence) {
    return new DiagnoseOutputModel.DiagnoseOutput(
        DiagnoseOutputModel.SCHEMA_VERSION,
        new DiagnoseOutputModel.RequestInfo("claude_code", "test-session", "/tmp/test"),
        new DiagnoseOutputModel.SourceInfo(
            "UNAVAILABLE", "", 0, "", 0, List.of(), "UNAVAILABLE", Map.of()),
        new DiagnoseOutputModel.RawInfo("UNAVAILABLE", 0, Map.of(), 0, 0, 0, 0, 0, List.of()),
        new DiagnoseOutputModel.NormalizationInfo("UNAVAILABLE", "", 0, 0, 0, 0, 0, 0, 0),
        new DiagnoseOutputModel.ProjectionInfo("UNAVAILABLE", 0, 0, 0, 0, 0),
        divergence,
        new DiagnoseOutputModel.TimingInfo(0, 0, 0, 0, 0),
        List.of());
  }
}
