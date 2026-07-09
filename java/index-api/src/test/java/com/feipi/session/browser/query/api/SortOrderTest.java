package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** {@link SortOrder} 契约测试。 */
class SortOrderTest {

  @Test
  void fromStringAcceptsLowerCase() {
    assertThat(SortOrder.fromString("asc")).isEqualTo(SortOrder.ASC);
    assertThat(SortOrder.fromString("desc")).isEqualTo(SortOrder.DESC);
  }

  @Test
  void fromStringCaseInsensitive() {
    assertThat(SortOrder.fromString("ASC")).isEqualTo(SortOrder.ASC);
    assertThat(SortOrder.fromString("Desc")).isEqualTo(SortOrder.DESC);
  }

  @Test
  void fromStringRejectsInvalid() {
    assertThatThrownBy(() -> SortOrder.fromString("invalid"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("无法识别的排序方向");
  }
}
