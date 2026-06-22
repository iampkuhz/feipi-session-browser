package com.feipi.session.browser.contracttest.sourceSpi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceDiagnostic} 契约测试。
 *
 * <p>验证诊断不变量：必填字段非 null、消息非空、行号为正整数。
 */
@DisplayName("Source SPI — SourceDiagnostic 契约")
class SourceDiagnosticContractTest {

  @Test
  @DisplayName("合法诊断可正常创建")
  void validDiagnosticCreated() {
    SourceDiagnostic diag =
        new SourceDiagnostic(
            ParseSeverity.ERROR, ParseIssueType.BAD_JSON, "JSON 格式损坏", 42, Optional.of("{bad"));
    assertThat(diag.severity()).isEqualTo(ParseSeverity.ERROR);
    assertThat(diag.issueType()).isEqualTo(ParseIssueType.BAD_JSON);
    assertThat(diag.message()).isEqualTo("JSON 格式损坏");
    assertThat(diag.lineNo()).isEqualTo(42);
    assertThat(diag.preview()).contains("{bad");
  }

  @Test
  @DisplayName("preview 可选")
  void previewOptional() {
    SourceDiagnostic diag =
        new SourceDiagnostic(
            ParseSeverity.WARNING, ParseIssueType.NON_OBJECT_SKIPPED, "跳过非对象", 1, Optional.empty());
    assertThat(diag.preview()).isEmpty();
  }

  @Test
  @DisplayName("null severity 抛出 NullPointerException")
  void nullSeverityRejected() {
    assertThatThrownBy(
            () -> new SourceDiagnostic(null, ParseIssueType.BAD_JSON, "msg", 1, Optional.empty()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("null issueType 抛出 NullPointerException")
  void nullIssueTypeRejected() {
    assertThatThrownBy(
            () -> new SourceDiagnostic(ParseSeverity.INFO, null, "msg", 1, Optional.empty()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("null message 抛出 NullPointerException")
  void nullMessageRejected() {
    assertThatThrownBy(
            () ->
                new SourceDiagnostic(
                    ParseSeverity.INFO, ParseIssueType.BAD_JSON, null, 1, Optional.empty()))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("空 message 抛出 IllegalArgumentException")
  void emptyMessageRejected() {
    assertThatThrownBy(
            () ->
                new SourceDiagnostic(
                    ParseSeverity.INFO, ParseIssueType.BAD_JSON, "", 1, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("message");
  }

  @Test
  @DisplayName("零行号抛出 IllegalArgumentException")
  void zeroLineNoRejected() {
    assertThatThrownBy(
            () ->
                new SourceDiagnostic(
                    ParseSeverity.INFO, ParseIssueType.BAD_JSON, "msg", 0, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("lineNo");
  }

  @Test
  @DisplayName("负行号抛出 IllegalArgumentException")
  void negativeLineNoRejected() {
    assertThatThrownBy(
            () ->
                new SourceDiagnostic(
                    ParseSeverity.INFO, ParseIssueType.BAD_JSON, "msg", -5, Optional.empty()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("lineNo");
  }

  @Test
  @DisplayName("ParseSeverity 三种级别全覆盖")
  void allSeveritiesExist() {
    assertThat(ParseSeverity.values()).hasSize(3);
    assertThat(ParseSeverity.valueOf("INFO")).isNotNull();
    assertThat(ParseSeverity.valueOf("WARNING")).isNotNull();
    assertThat(ParseSeverity.valueOf("ERROR")).isNotNull();
  }

  @Test
  @DisplayName("ParseIssueType 三种类型全覆盖")
  void allIssueTypesExist() {
    assertThat(ParseIssueType.values()).hasSize(3);
    assertThat(ParseIssueType.valueOf("BAD_JSON")).isNotNull();
    assertThat(ParseIssueType.valueOf("NON_OBJECT_SKIPPED")).isNotNull();
    assertThat(ParseIssueType.valueOf("CONCATENATED_OBJECTS")).isNotNull();
  }
}
