package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/** {@link Sort} 契约测试。 */
class SortTest {

  @Test
  void defaultSessionIsEndedAtDesc() {
    assertThat(Sort.DEFAULT_SESSION.sortKey()).isEqualTo("ended_at");
    assertThat(Sort.DEFAULT_SESSION.order()).isEqualTo(SortOrder.DESC);
  }

  @Test
  void defaultProjectIsLastActiveDesc() {
    assertThat(Sort.DEFAULT_PROJECT.sortKey()).isEqualTo("last_active");
    assertThat(Sort.DEFAULT_PROJECT.order()).isEqualTo(SortOrder.DESC);
  }

  @Test
  void ofSessionFromEnum() {
    Sort sort = Sort.ofSession(SessionSortField.TOTAL_TOKENS, SortOrder.ASC);
    assertThat(sort.sortKey()).isEqualTo("total_tokens");
    assertThat(sort.order()).isEqualTo(SortOrder.ASC);
    assertThat(sort.toSqlFragment()).isEqualTo("total_tokens ASC");
  }

  @Test
  void ofProjectFromEnum() {
    Sort sort = Sort.ofProject(ProjectSortField.TOTAL_SESSIONS, SortOrder.DESC);
    assertThat(sort.sortKey()).isEqualTo("total_sessions");
    assertThat(sort.order()).isEqualTo(SortOrder.DESC);
    assertThat(sort.toSqlFragment()).isEqualTo("total_sessions DESC");
  }

  @Test
  void ofSessionFromString() {
    Sort sort = Sort.ofSession("ended_at", "desc");
    assertThat(sort.sortKey()).isEqualTo("ended_at");
    assertThat(sort.order()).isEqualTo(SortOrder.DESC);
  }

  @Test
  void ofProjectFromString() {
    Sort sort = Sort.ofProject("total_tokens", "asc");
    assertThat(sort.sortKey()).isEqualTo("total_tokens");
    assertThat(sort.order()).isEqualTo(SortOrder.ASC);
  }

  @Test
  void equalsAndHashCode() {
    Sort a = Sort.ofSession(SessionSortField.ENDED_AT, SortOrder.DESC);
    Sort b = Sort.ofSession("ended_at", "desc");
    assertThat(a).isEqualTo(b);
    assertThat(a.hashCode()).isEqualTo(b.hashCode());
  }

  @Test
  void notEqualDifferentField() {
    Sort a = Sort.ofSession(SessionSortField.ENDED_AT, SortOrder.DESC);
    Sort b = Sort.ofSession(SessionSortField.TOTAL_TOKENS, SortOrder.DESC);
    assertThat(a).isNotEqualTo(b);
  }

  @Test
  void notEqualDifferentOrder() {
    Sort a = Sort.ofSession(SessionSortField.ENDED_AT, SortOrder.DESC);
    Sort b = Sort.ofSession(SessionSortField.ENDED_AT, SortOrder.ASC);
    assertThat(a).isNotEqualTo(b);
  }

  @Test
  void toStringContainsSortKey() {
    Sort sort = Sort.ofSession(SessionSortField.ENDED_AT, SortOrder.DESC);
    assertThat(sort.toString()).contains("ended_at").contains("DESC");
  }
}
