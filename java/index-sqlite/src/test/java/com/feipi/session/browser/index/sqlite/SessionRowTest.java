package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link SessionRow} 测试，覆盖不变量验证和默认值处理。 */
@DisplayName("SessionRow 测试")
class SessionRowTest {

  /** 构建最小有效 SessionRow 用于测试。 */
  private static SessionRow minimalValidRow() {
    return new SessionRow(
        "claude_code:test-id",
        "claude_code",
        "test-id",
        "标题",
        "project-1",
        "Project One",
        "/cwd",
        "2025-01-01T00:00:00Z",
        "2025-01-01T01:00:00Z",
        3600.0,
        100.0,
        50.0,
        "claude-3",
        "main",
        "cli",
        5,
        10,
        20,
        1000,
        2000,
        500,
        300,
        3800,
        0,
        0,
        1700000000.0,
        1700000000.0,
        "/path/to/file.jsonl");
  }

  @Nested
  @DisplayName("构造器不变量")
  class ConstructorInvariants {

    @Test
    @DisplayName("有效字段创建成功")
    void validRowCreation() {
      SessionRow row = minimalValidRow();
      assertThat(row.sessionKey()).isEqualTo("claude_code:test-id");
      assertThat(row.agent()).isEqualTo("claude_code");
      assertThat(row.sessionId()).isEqualTo("test-id");
      assertThat(row.title()).isEqualTo("标题");
    }

    @Test
    @DisplayName("sessionKey 为空字符串时抛异常")
    void emptySessionKeyRejected() {
      assertThatThrownBy(
              () ->
                  new SessionRow(
                      "",
                      "claude_code",
                      "test-id",
                      null,
                      "project-1",
                      null,
                      null,
                      null,
                      "2025-01-01T00:00:00Z",
                      0,
                      0,
                      0,
                      null,
                      null,
                      null,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      null))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sessionKey");
    }

    @Test
    @DisplayName("agent 为空字符串时抛异常")
    void emptyAgentRejected() {
      assertThatThrownBy(
              () ->
                  new SessionRow(
                      "claude_code:test-id",
                      "",
                      "test-id",
                      null,
                      "project-1",
                      null,
                      null,
                      null,
                      "2025-01-01T00:00:00Z",
                      0,
                      0,
                      0,
                      null,
                      null,
                      null,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      null))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("agent");
    }

    @Test
    @DisplayName("sessionId 为空字符串时抛异常")
    void emptySessionIdRejected() {
      assertThatThrownBy(
              () ->
                  new SessionRow(
                      "claude_code:test-id",
                      "claude_code",
                      "",
                      null,
                      "project-1",
                      null,
                      null,
                      null,
                      "2025-01-01T00:00:00Z",
                      0,
                      0,
                      0,
                      null,
                      null,
                      null,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      null))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sessionId");
    }

    @Test
    @DisplayName("endedAt 为空字符串时抛异常")
    void emptyEndedAtRejected() {
      assertThatThrownBy(
              () ->
                  new SessionRow(
                      "claude_code:test-id",
                      "claude_code",
                      "test-id",
                      null,
                      "project-1",
                      null,
                      null,
                      null,
                      "",
                      0,
                      0,
                      0,
                      null,
                      null,
                      null,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      null))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("endedAt");
    }

    @Test
    @DisplayName("负数 durationSeconds 时抛异常")
    void negativeDurationRejected() {
      assertThatThrownBy(
              () ->
                  new SessionRow(
                      "claude_code:test-id",
                      "claude_code",
                      "test-id",
                      null,
                      "project-1",
                      null,
                      null,
                      null,
                      "2025-01-01T00:00:00Z",
                      -1.0,
                      0,
                      0,
                      null,
                      null,
                      null,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      null))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("durationSeconds");
    }

    @Test
    @DisplayName("负数 token 字段时抛异常")
    void negativeTokenRejected() {
      assertThatThrownBy(
              () ->
                  new SessionRow(
                      "claude_code:test-id",
                      "claude_code",
                      "test-id",
                      null,
                      "project-1",
                      null,
                      null,
                      null,
                      "2025-01-01T00:00:00Z",
                      0,
                      0,
                      0,
                      null,
                      null,
                      null,
                      0,
                      0,
                      0,
                      -1,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      0,
                      null))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("outputTokens");
    }
  }

  @Nested
  @DisplayName("默认值处理")
  class DefaultValues {

    @Test
    @DisplayName("null 字符串字段默认转换为空字符串")
    void nullStringsDefaultToEmpty() {
      SessionRow row =
          new SessionRow(
              "claude_code:test-id",
              "claude_code",
              "test-id",
              null,
              null,
              null,
              null,
              null,
              "2025-01-01T00:00:00Z",
              0,
              0,
              0,
              null,
              null,
              null,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              null);

      assertThat(row.title()).isEmpty();
      assertThat(row.projectKey()).isEmpty();
      assertThat(row.projectName()).isEmpty();
      assertThat(row.cwd()).isEmpty();
      assertThat(row.startedAt()).isEmpty();
      assertThat(row.model()).isEmpty();
      assertThat(row.gitBranch()).isEmpty();
      assertThat(row.source()).isEmpty();
      assertThat(row.filePath()).isEmpty();
    }

    @Test
    @DisplayName("零值数值字段创建成功")
    void zeroNumericFieldsAllowed() {
      SessionRow row =
          new SessionRow(
              "claude_code:test-id",
              "claude_code",
              "test-id",
              null,
              null,
              null,
              null,
              null,
              "2025-01-01T00:00:00Z",
              0,
              0,
              0,
              null,
              null,
              null,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              null);

      assertThat(row.durationSeconds()).isZero();
      assertThat(row.totalTokens()).isZero();
      assertThat(row.userMessageCount()).isZero();
    }
  }
}
