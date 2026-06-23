package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/**
 * {@link TierConfig} 单元测试。
 *
 * <p>覆盖构造器验证、默认值常量和 record 语义。
 */
class TierConfigTest {

  @Test
  void validConfigCreation() {
    TierConfig config = new TierConfig(300, 30);
    assertThat(config.windowSeconds()).isEqualTo(300);
    assertThat(config.intervalSeconds()).isEqualTo(30);
  }

  @Test
  void zeroWindowThrows() {
    assertThatThrownBy(() -> new TierConfig(0, 30))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("windowSeconds");
  }

  @Test
  void negativeIntervalThrows() {
    assertThatThrownBy(() -> new TierConfig(300, -1))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("intervalSeconds");
  }

  @Test
  void defaultConstants() {
    assertThat(TierConfig.DEFAULT_HOT.windowSeconds()).isEqualTo(30 * 60);
    assertThat(TierConfig.DEFAULT_HOT.intervalSeconds()).isEqualTo(30);
    assertThat(TierConfig.DEFAULT_WARM.windowSeconds()).isEqualTo(24 * 3600);
    assertThat(TierConfig.DEFAULT_WARM.intervalSeconds()).isEqualTo(5 * 60);
  }

  @Test
  void equalitySemantics() {
    TierConfig a = new TierConfig(100, 10);
    TierConfig b = new TierConfig(100, 10);
    TierConfig c = new TierConfig(200, 10);
    assertThat(a).isEqualTo(b);
    assertThat(a).isNotEqualTo(c);
    assertThat(a.hashCode()).isEqualTo(b.hashCode());
  }
}
