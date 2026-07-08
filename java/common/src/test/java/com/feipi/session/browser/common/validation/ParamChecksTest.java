package com.feipi.session.browser.common.validation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link ParamChecks} 单元测试。 */
@DisplayName("ParamChecks")
class ParamChecksTest {

  @Test
  @DisplayName("非负校验保留字段值")
  void nonNegativeReturnsOriginalValue() {
    assertThat(ParamChecks.nonNegative(3L, "count")).isEqualTo(3L);
  }

  @Test
  @DisplayName("负数校验错误包含字段名")
  void nonNegativeRejectsNegativeValue() {
    assertThatThrownBy(() -> ParamChecks.nonNegative(-1L, "count"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("count");
  }

  @Test
  @DisplayName("空白字符串校验失败")
  void nonBlankRejectsBlankValue() {
    assertThatThrownBy(() -> ParamChecks.nonBlank("  ", "name"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("name");
  }

  @Test
  @DisplayName("非空字符串校验对 null 保留 NPE 语义")
  void nonEmptyRejectsNullWithNpe() {
    assertThatThrownBy(() -> ParamChecks.nonEmpty(null, "id"))
        .isInstanceOf(NullPointerException.class)
        .hasMessageContaining("id");
  }

  @Test
  @DisplayName("required 对 null 抛出参数异常")
  void requiredRejectsNullValue() {
    assertThatThrownBy(() -> ParamChecks.required(null, "config"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("config");
  }

  @Test
  @DisplayName("范围校验覆盖上下界")
  void inRangeAcceptsBounds() {
    assertThat(ParamChecks.inRange(0, 0, 65535, "port")).isZero();
    assertThat(ParamChecks.inRange(65535, 0, 65535, "port")).isEqualTo(65535);
  }
}
