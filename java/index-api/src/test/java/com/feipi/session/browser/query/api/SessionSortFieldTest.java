package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** {@link SessionSortField} 契约测试。 */
class SessionSortFieldTest {

  @Test
  void columnNameMatchesDatabaseColumn() {
    assertThat(SessionSortField.ENDED_AT.getColumnName()).isEqualTo("ended_at");
    assertThat(SessionSortField.TOTAL_TOKENS.getColumnName()).isEqualTo("total_tokens");
    assertThat(SessionSortField.FAILED_TOOL_COUNT.getColumnName()).isEqualTo("failed_tool_count");
  }

  @Test
  void fromStringMatchesByColumnName() {
    assertThat(SessionSortField.fromString("ended_at")).isEqualTo(SessionSortField.ENDED_AT);
    assertThat(SessionSortField.fromString("total_tokens"))
        .isEqualTo(SessionSortField.TOTAL_TOKENS);
  }

  @Test
  void fromStringMatchesByEnumName() {
    assertThat(SessionSortField.fromString("ENDED_AT")).isEqualTo(SessionSortField.ENDED_AT);
    assertThat(SessionSortField.fromString("ended_at")).isEqualTo(SessionSortField.ENDED_AT);
  }

  @Test
  void fromStringCaseInsensitive() {
    assertThat(SessionSortField.fromString("Ended_At")).isEqualTo(SessionSortField.ENDED_AT);
  }

  @Test
  void fromStringRejectsInvalid() {
    assertThatThrownBy(() -> SessionSortField.fromString("nonexistent"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("无法识别的会话排序字段");
  }

  @Test
  void fromStringRejectsNull() {
    assertThatThrownBy(() -> SessionSortField.fromString(null))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  void allEnumValuesHaveNonEmptyColumnName() {
    for (SessionSortField field : SessionSortField.values()) {
      assertThat(field.getColumnName()).isNotEmpty();
    }
  }
}
