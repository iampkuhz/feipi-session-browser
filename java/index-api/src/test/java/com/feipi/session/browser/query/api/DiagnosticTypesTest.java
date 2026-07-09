package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 诊断相关类型单元测试。
 *
 * <p>覆盖 {@link DiagnosticSeverity} 和 {@link DiagnosticIssue} 的不变量和边界条件。
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
}
