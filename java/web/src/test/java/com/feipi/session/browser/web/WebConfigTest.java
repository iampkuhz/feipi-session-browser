package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link WebConfig} 单元测试。
 *
 * <p>验证配置不可变性、默认值、参数校验。
 */
@DisplayName("WebConfig 配置测试")
class WebConfigTest {

  @Test
  @DisplayName("默认配置使用回环地址和随机端口")
  void defaultsUseLoopbackAndRandomPort() {
    WebConfig config = WebConfig.defaults();

    assertThat(config.host()).isEqualTo("127.0.0.1");
    assertThat(config.port()).isEqualTo(0);
    assertThat(config.staticPath()).isNull();
  }

  @Test
  @DisplayName("指定端口配置保留端口值")
  void withPortRetainsPortValue() {
    WebConfig config = WebConfig.withPort(8080);

    assertThat(config.host()).isEqualTo("127.0.0.1");
    assertThat(config.port()).isEqualTo(8080);
    assertThat(config.staticPath()).isNull();
  }

  @Test
  @DisplayName("自定义完整配置保留所有值")
  void fullConfigRetainsAllValues() {
    WebConfig config = new WebConfig("0.0.0.0", 9090, "/static");

    assertThat(config.host()).isEqualTo("0.0.0.0");
    assertThat(config.port()).isEqualTo(9090);
    assertThat(config.staticPath()).isEqualTo("/static");
  }

  @Test
  @DisplayName("空 host 抛出 IllegalArgumentException")
  void emptyHostThrows() {
    assertThatThrownBy(() -> new WebConfig("", 8080, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("host");
  }

  @Test
  @DisplayName("空白 host 抛出 IllegalArgumentException")
  void blankHostThrows() {
    assertThatThrownBy(() -> new WebConfig("   ", 8080, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("host");
  }

  @Test
  @DisplayName("null host 抛出 IllegalArgumentException")
  void nullHostThrows() {
    assertThatThrownBy(() -> new WebConfig(null, 8080, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("host");
  }

  @Test
  @DisplayName("负数端口抛出 IllegalArgumentException")
  void negativePortThrows() {
    assertThatThrownBy(() -> new WebConfig("127.0.0.1", -1, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("端口");
  }

  @Test
  @DisplayName("超大端口抛出 IllegalArgumentException")
  void portAbove65535Throws() {
    assertThatThrownBy(() -> new WebConfig("127.0.0.1", 70000, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("端口");
  }

  @Test
  @DisplayName("端口 0 合法（随机端口）")
  void portZeroIsValid() {
    WebConfig config = new WebConfig("127.0.0.1", 0, null);
    assertThat(config.port()).isEqualTo(0);
  }

  @Test
  @DisplayName("端口 65535 合法（最大端口）")
  void portMaxIsValid() {
    WebConfig config = new WebConfig("127.0.0.1", 65535, null);
    assertThat(config.port()).isEqualTo(65535);
  }
}
