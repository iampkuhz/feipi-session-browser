package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** {@link ProjectSortField} 契约测试。 */
class ProjectSortFieldTest {

  @Test
  void sortKeyMatchesBusinessKey() {
    assertThat(ProjectSortField.TOTAL_SESSIONS.getSortKey()).isEqualTo("total_sessions");
    assertThat(ProjectSortField.LAST_ACTIVE.getSortKey()).isEqualTo("last_active");
    assertThat(ProjectSortField.TOTAL_TOKENS.getSortKey()).isEqualTo("total_tokens");
  }

  @Test
  void fromStringMatchesBySortKey() {
    assertThat(ProjectSortField.fromString("total_sessions"))
        .isEqualTo(ProjectSortField.TOTAL_SESSIONS);
    assertThat(ProjectSortField.fromString("last_active")).isEqualTo(ProjectSortField.LAST_ACTIVE);
  }

  @Test
  void fromStringMatchesByEnumName() {
    assertThat(ProjectSortField.fromString("TOTAL_SESSIONS"))
        .isEqualTo(ProjectSortField.TOTAL_SESSIONS);
  }

  @Test
  void fromStringRejectsInvalid() {
    assertThatThrownBy(() -> ProjectSortField.fromString("nonexistent"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("无法识别的项目排序字段");
  }

  @Test
  void fromStringRejectsNull() {
    assertThatThrownBy(() -> ProjectSortField.fromString(null))
        .isInstanceOf(NullPointerException.class);
  }
}
