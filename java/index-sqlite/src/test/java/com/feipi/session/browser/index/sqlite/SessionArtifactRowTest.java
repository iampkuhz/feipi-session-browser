package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link SessionArtifactRow} 测试，覆盖不变量验证。 */
@DisplayName("SessionArtifactRow 测试")
class SessionArtifactRowTest {

  @Nested
  @DisplayName("构造器不变量")
  class ConstructorInvariants {

    @Test
    @DisplayName("有效字段创建成功")
    void validRowCreation() {
      SessionArtifactRow row =
          new SessionArtifactRow(
              "claude_code:test-id",
              "normalized",
              "/path/to/artifact.json",
              "session-detail.normalized.v3",
              "/source/file.jsonl",
              1700000000.0,
              12345,
              1700000000.0,
              1700000000.0);

      assertThat(row.sessionKey()).isEqualTo("claude_code:test-id");
      assertThat(row.artifactType()).isEqualTo("normalized");
      assertThat(row.path()).isEqualTo("/path/to/artifact.json");
      assertThat(row.sizeBytes()).isEqualTo(12345);
    }

    @Test
    @DisplayName("sessionKey 为空字符串时抛异常")
    void emptySessionKeyRejected() {
      assertThatThrownBy(
              () -> new SessionArtifactRow("", "normalized", "/path", null, null, 0, 0, 0, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sessionKey");
    }

    @Test
    @DisplayName("artifactType 为空字符串时抛异常")
    void emptyArtifactTypeRejected() {
      assertThatThrownBy(
              () ->
                  new SessionArtifactRow(
                      "claude_code:test-id", "", "/path", null, null, 0, 0, 0, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("artifactType");
    }

    @Test
    @DisplayName("负数 sizeBytes 时抛异常")
    void negativeSizeBytesRejected() {
      assertThatThrownBy(
              () ->
                  new SessionArtifactRow(
                      "claude_code:test-id", "normalized", "/path", null, null, 0, -1, 0, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sizeBytes");
    }

    @Test
    @DisplayName("负数 sourceMtime 时抛异常")
    void negativeSourceMtimeRejected() {
      assertThatThrownBy(
              () ->
                  new SessionArtifactRow(
                      "claude_code:test-id", "normalized", "/path", null, null, -1.0, 0, 0, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sourceMtime");
    }
  }

  @Nested
  @DisplayName("默认值处理")
  class DefaultValues {

    @Test
    @DisplayName("null 字符串字段默认转换为空字符串")
    void nullStringsDefaultToEmpty() {
      SessionArtifactRow row =
          new SessionArtifactRow("claude_code:test-id", "normalized", null, null, null, 0, 0, 0, 0);

      assertThat(row.path()).isEmpty();
      assertThat(row.schemaVersion()).isEmpty();
      assertThat(row.sourcePath()).isEmpty();
    }
  }
}
