package com.feipi.session.browser.common.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link TokenChecks} 单元测试。 */
@DisplayName("TokenChecks")
class TokenChecksTest {

  @Test
  @DisplayName("四段 token 合计计算")
  void componentTotalSumsSegments() {
    assertThat(TokenChecks.componentTotal(1, 2, 3, 4)).isEqualTo(10);
  }

  @Test
  @DisplayName("标准 token 字段校验 total 等于四段合计")
  void requireTokenSegmentsRejectsMismatchedTotal() {
    assertThatThrownBy(() -> TokenChecks.requireTokenSegments(1, 2, 3, 4, 11))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("component sum");
  }

  @Test
  @DisplayName("usage token 合计错误同时保留 component 和 token segment 语义")
  void requireUsageSegmentsRejectsMismatchedTotal() {
    assertThatThrownBy(() -> TokenChecks.requireUsageSegments(1, 2, 3, 4, 11, "usage"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("component sum")
        .hasMessageContaining("token segment sum");
  }

  @Test
  @DisplayName("usage token 字段错误消息包含前缀")
  void requireUsageSegmentsUsesPrefix() {
    assertThatThrownBy(() -> TokenChecks.requireUsageSegments(-1, 0, 0, 0, 0, "usage"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("usage.fresh");
  }
}
