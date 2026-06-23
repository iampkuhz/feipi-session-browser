package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 诊断相关类型单元测试。
 *
 * <p>覆盖 {@link DiagnosticSeverity}、{@link DiagnosticIssue}、{@link DiagnosticIssueItem} 和 {@link
 * SessionParseDiagnostics} 的不变量和边界条件。
 */
@DisplayName("诊断类型契约测试")
class DiagnosticTypesTest {

  @Nested
  @DisplayName("DiagnosticSeverity")
  class DiagnosticSeverityTests {

    @Test
    @DisplayName("枚举值完整")
    void enumValuesComplete() {
      assertThat(DiagnosticSeverity.values())
          .containsExactly(
              DiagnosticSeverity.INFO, DiagnosticSeverity.WARNING, DiagnosticSeverity.CRITICAL);
    }
  }

  @Nested
  @DisplayName("DiagnosticIssue")
  class DiagnosticIssueTests {

    @Test
    @DisplayName("fromValue 返回正确枚举")
    void fromValueReturnsEnum() {
      assertThat(DiagnosticIssue.fromValue("BAD_JSON")).isEqualTo(DiagnosticIssue.BAD_JSON);
      assertThat(DiagnosticIssue.fromValue("EMPTY_FILE")).isEqualTo(DiagnosticIssue.EMPTY_FILE);
      assertThat(DiagnosticIssue.fromValue("TOKEN_ESTIMATED"))
          .isEqualTo(DiagnosticIssue.TOKEN_ESTIMATED);
    }

    @Test
    @DisplayName("fromValue 未知值抛出异常")
    void fromValueUnknownThrows() {
      assertThatThrownBy(() -> DiagnosticIssue.fromValue("UNKNOWN"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("无法识别的诊断问题类别");
    }

    @Test
    @DisplayName("getValue 返回稳定协议值")
    void getValueReturnsStableValue() {
      assertThat(DiagnosticIssue.BAD_JSON.getValue()).isEqualTo("BAD_JSON");
      assertThat(DiagnosticIssue.FILE_NOT_FOUND.getValue()).isEqualTo("FILE_NOT_FOUND");
    }
  }

  @Nested
  @DisplayName("DiagnosticIssueItem")
  class DiagnosticIssueItemTests {

    @Test
    @DisplayName("fileLevel 创建行号为 0 的问题")
    void fileLevelCreatesZeroLineNo() {
      DiagnosticIssueItem item =
          DiagnosticIssueItem.fileLevel(
              DiagnosticIssue.FILE_NOT_FOUND, DiagnosticSeverity.CRITICAL, "文件缺失");
      assertThat(item.lineNo()).isZero();
      assertThat(item.detail()).isEmpty();
    }

    @Test
    @DisplayName("withDetail 创建带详情的行级问题")
    void withDetailCreatesRowLevelIssue() {
      DiagnosticIssueItem item =
          DiagnosticIssueItem.withDetail(
              DiagnosticIssue.BAD_JSON, DiagnosticSeverity.WARNING, "JSON 解析失败", 42, "预览内容");
      assertThat(item.lineNo()).isEqualTo(42);
      assertThat(item.detail()).isEqualTo("预览内容");
    }

    @Test
    @DisplayName("负行号抛出异常")
    void negativeLineNoThrows() {
      assertThatThrownBy(
              () ->
                  new DiagnosticIssueItem(
                      DiagnosticIssue.BAD_JSON,
                      DiagnosticSeverity.WARNING,
                      "message",
                      -1,
                      "detail"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("lineNo 必须非负");
    }

    @Test
    @DisplayName("null detail 转换为空字符串")
    void nullDetailBecomesEmpty() {
      DiagnosticIssueItem item =
          new DiagnosticIssueItem(
              DiagnosticIssue.BAD_JSON, DiagnosticSeverity.WARNING, "message", 0, null);
      assertThat(item.detail()).isEmpty();
    }
  }

  @Nested
  @DisplayName("SessionParseDiagnostics")
  class SessionParseDiagnosticsTests {

    @Test
    @DisplayName("empty 创建无问题的诊断")
    void emptyCreatesNoIssues() {
      SessionParseDiagnostics diag = SessionParseDiagnostics.empty("key1", "/path/to/file");
      assertThat(diag.sessionKey()).isEqualTo("key1");
      assertThat(diag.filePath()).isEqualTo("/path/to/file");
      assertThat(diag.issues()).isEmpty();
      assertThat(diag.hasCritical()).isFalse();
      assertThat(diag.hasWarnings()).isFalse();
      assertThat(diag.criticalCount()).isZero();
      assertThat(diag.warningCount()).isZero();
      assertThat(diag.infoCount()).isZero();
    }

    @Test
    @DisplayName("hasCritical 检测严重问题")
    void hasCriticalDetectsCritical() {
      SessionParseDiagnostics diag =
          new SessionParseDiagnostics(
              "key1",
              "/path",
              100,
              50,
              10,
              List.of(
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.BAD_JSON, DiagnosticSeverity.CRITICAL, "严重错误")));
      assertThat(diag.hasCritical()).isTrue();
      assertThat(diag.criticalCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("hasWarnings 检测警告问题")
    void hasWarningsDetectsWarnings() {
      SessionParseDiagnostics diag =
          new SessionParseDiagnostics(
              "key1",
              "/path",
              100,
              50,
              10,
              List.of(
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.TOKEN_ESTIMATED, DiagnosticSeverity.WARNING, "估算 token")));
      assertThat(diag.hasWarnings()).isTrue();
      assertThat(diag.warningCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("infoCount 统计信息级问题")
    void infoCountCountsInfo() {
      SessionParseDiagnostics diag =
          new SessionParseDiagnostics(
              "key1",
              "/path",
              100,
              50,
              10,
              List.of(
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.TOKEN_ESTIMATED, DiagnosticSeverity.INFO, "信息"),
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.TOKEN_ESTIMATED, DiagnosticSeverity.INFO, "信息 2")));
      assertThat(diag.infoCount()).isEqualTo(2);
    }

    @Test
    @DisplayName("负计数字段抛出异常")
    void negativeCountThrows() {
      assertThatThrownBy(() -> new SessionParseDiagnostics("key1", "/path", -1, 0, 0, List.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("totalLines 必须非负");
    }

    @Test
    @DisplayName("不可变问题列表防止修改")
    void immutableIssuesListPreventsModification() {
      SessionParseDiagnostics diag = SessionParseDiagnostics.empty("key1", "/path");
      assertThatThrownBy(
              () ->
                  diag.issues()
                      .add(
                          DiagnosticIssueItem.fileLevel(
                              DiagnosticIssue.BAD_JSON, DiagnosticSeverity.WARNING, "test")))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }
}
