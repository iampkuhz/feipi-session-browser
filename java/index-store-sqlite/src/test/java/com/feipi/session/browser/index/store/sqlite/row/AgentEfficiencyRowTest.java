package com.feipi.session.browser.index.store.sqlite.row;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * {@link AgentEfficiencyRow} 测试，覆盖 Jakarta validation 迁移后的不变量验证。
 *
 * <p>重点覆盖比率字段、可选数值字段和计数字段的边界条件。
 */
@DisplayName("AgentEfficiencyRow 测试")
class AgentEfficiencyRowTest {

  /** 构建最小有效 AgentEfficiencyRow 用于测试。 */
  private static AgentEfficiencyRow minimalValidRow() {
    return new AgentEfficiencyRow(
        "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, 0.5, 0.1);
  }

  @Nested
  @DisplayName("构造器不变量")
  class ConstructorInvariants {

    @Test
    @DisplayName("有效字段创建成功")
    void validRowCreation() {
      AgentEfficiencyRow row = minimalValidRow();
      assertThat(row.agent()).isEqualTo("claude_code");
      assertThat(row.model()).isEqualTo("claude-3");
      assertThat(row.sessionCount()).isEqualTo(10L);
    }

    @Test
    @DisplayName("sessionCount=-1 抛 ConstraintViolationException")
    void negativeSessionCountRejected() {
      assertThatThrownBy(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", -1L, 100.0, 200.0, 5000L, 5.0, 1.5, 0.5, 0.1))
          .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    @DisplayName("cacheReuseRatio=1.01 不抛（@Ratio 仅校验非负有限数，不设上限）")
    void cacheReuseRatioAboveOneAccepted() {
      assertThatCode(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, 1.01, 0.1))
          .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("cacheReuseRatio=-0.01 抛 ConstraintViolationException（@Ratio 校验非负）")
    void negativeCacheReuseRatioRejected() {
      assertThatThrownBy(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, -0.01, 0.1))
          .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    @DisplayName("cacheReuseRatio=NaN 抛 ConstraintViolationException（@Ratio 拒绝 NaN）")
    void nanCacheReuseRatioRejected() {
      assertThatThrownBy(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code",
                      "claude-3",
                      10L,
                      100.0,
                      200.0,
                      5000L,
                      5.0,
                      1.5,
                      Double.NaN,
                      0.1))
          .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    @DisplayName("cacheReuseRatio=1.0 不抛（边界有效值）")
    void cacheReuseRatioAtOneIsAccepted() {
      assertThatCode(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, 1.0, 0.1))
          .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("toolsPerRound=null 不抛（可选字段）")
    void nullToolsPerRoundAccepted() {
      assertThatCode(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, null, 0.5, 0.1))
          .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("toolsPerRound=-0.1 抛 ConstraintViolationException（@PositiveOrZero）")
    void negativeToolsPerRoundRejected() {
      assertThatThrownBy(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, -0.1, 0.5, 0.1))
          .isInstanceOf(ConstraintViolationException.class);
    }

    @Test
    @DisplayName("agent 为空字符串抛 ConstraintViolationException")
    void emptyAgentRejected() {
      assertThatThrownBy(
              () ->
                  new AgentEfficiencyRow(
                      "", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, 0.5, 0.1))
          .isInstanceOf(ConstraintViolationException.class);
    }
  }

  @Nested
  @DisplayName("可选字段 null 语义")
  class OptionalNullSemantics {

    @Test
    @DisplayName("cacheReuseRatio=null 不抛（无数据语义）")
    void nullCacheReuseRatioAccepted() {
      assertThatCode(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, null, 0.1))
          .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("failedPerSession=null 不抛（无数据语义）")
    void nullFailedPerSessionAccepted() {
      assertThatCode(
              () ->
                  new AgentEfficiencyRow(
                      "claude_code", "claude-3", 10L, 100.0, 200.0, 5000L, 5.0, 1.5, 0.5, null))
          .doesNotThrowAnyException();
    }

    @Test
    @DisplayName("所有可选 Double 字段为 null 时创建成功")
    void allOptionalDoublesNull() {
      AgentEfficiencyRow row =
          new AgentEfficiencyRow(
              "claude_code", "claude-3", 0L, 0.0, 0.0, 0L, 0.0, null, null, null);
      assertThat(row.toolsPerRound()).isNull();
      assertThat(row.cacheReuseRatio()).isNull();
      assertThat(row.failedPerSession()).isNull();
    }
  }
}
