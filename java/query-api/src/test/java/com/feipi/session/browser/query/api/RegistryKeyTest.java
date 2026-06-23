package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 注册键枚举单元测试。
 *
 * <p>覆盖 {@link SessionAnomalyKey} 和 {@link RoundSignalKey} 的不变量和边界条件。
 */
@DisplayName("注册键枚举测试")
class RegistryKeyTest {

  @Nested
  @DisplayName("SessionAnomalyKey")
  class SessionAnomalyKeyTests {

    @Test
    @DisplayName("fromValue 返回正确枚举")
    void fromValueReturnsEnum() {
      assertThat(SessionAnomalyKey.fromValue("long_duration")).isEqualTo(SessionAnomalyKey.LONG_DURATION);
      assertThat(SessionAnomalyKey.fromValue("failed_run")).isEqualTo(SessionAnomalyKey.FAILED_RUN);
      assertThat(SessionAnomalyKey.fromValue("cache_write_spike"))
          .isEqualTo(SessionAnomalyKey.CACHE_WRITE_SPIKE);
    }

    @Test
    @DisplayName("fromValue 未知值抛出异常")
    void fromValueUnknownThrows() {
      assertThatThrownBy(() -> SessionAnomalyKey.fromValue("unknown"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("无法识别的会话异常键");
    }

    @Test
    @DisplayName("getValue 返回稳定协议值")
    void getValueReturnsStableValue() {
      assertThat(SessionAnomalyKey.LONG_DURATION.getValue()).isEqualTo("long_duration");
      assertThat(SessionAnomalyKey.FAILED_RUN.getValue()).isEqualTo("failed_run");
    }

    @Test
    @DisplayName("枚举值完整")
    void enumValuesComplete() {
      assertThat(SessionAnomalyKey.values()).hasSize(3);
    }
  }

  @Nested
  @DisplayName("RoundSignalKey")
  class RoundSignalKeyTests {

    @Test
    @DisplayName("fromValue 返回正确枚举")
    void fromValueReturnsEnum() {
      assertThat(RoundSignalKey.fromValue("failed-tool")).isEqualTo(RoundSignalKey.FAILED_TOOL);
      assertThat(RoundSignalKey.fromValue("llm-error")).isEqualTo(RoundSignalKey.LLM_ERROR);
      assertThat(RoundSignalKey.fromValue("long-tool")).isEqualTo(RoundSignalKey.LONG_TOOL);
      assertThat(RoundSignalKey.fromValue("tool-burst")).isEqualTo(RoundSignalKey.TOOL_BURST);
      assertThat(RoundSignalKey.fromValue("high-write")).isEqualTo(RoundSignalKey.HIGH_WRITE);
      assertThat(RoundSignalKey.fromValue("large-input")).isEqualTo(RoundSignalKey.LARGE_INPUT);
    }

    @Test
    @DisplayName("fromValue 未知值抛出异常")
    void fromValueUnknownThrows() {
      assertThatThrownBy(() -> RoundSignalKey.fromValue("unknown"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("无法识别的轮次信号键");
    }

    @Test
    @DisplayName("getValue 返回稳定协议值")
    void getValueReturnsStableValue() {
      assertThat(RoundSignalKey.FAILED_TOOL.getValue()).isEqualTo("failed-tool");
      assertThat(RoundSignalKey.LARGE_INPUT.getValue()).isEqualTo("large-input");
    }

    @Test
    @DisplayName("枚举值完整")
    void enumValuesComplete() {
      assertThat(RoundSignalKey.values()).hasSize(6);
    }
  }
}
