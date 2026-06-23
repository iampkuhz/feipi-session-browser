package com.feipi.session.browser.contracttest.sourcespi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.SourceId;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * {@link SourceId} 枚举契约测试。
 *
 * <p>验证三种源标识的完整性、序列化值和反序列化行为。 覆盖正向路径和负向路径。
 */
@DisplayName("Source SPI — SourceId 枚举契约")
class SourceIdContractTest {

  @Test
  @DisplayName("三种源标识全部存在")
  void allThreeSourcesExist() {
    assertThat(SourceId.values()).hasSize(3);
    assertThat(SourceId.valueOf("CLAUDE_CODE")).isNotNull();
    assertThat(SourceId.valueOf("CODEX")).isNotNull();
    assertThat(SourceId.valueOf("QODER")).isNotNull();
  }

  @Test
  @DisplayName("getValue() 返回约定的字符串标识")
  void getValueReturnsExpectedStrings() {
    assertThat(SourceId.CLAUDE_CODE.getValue()).isEqualTo("claude_code");
    assertThat(SourceId.CODEX.getValue()).isEqualTo("codex");
    assertThat(SourceId.QODER.getValue()).isEqualTo("qoder");
  }

  @Test
  @DisplayName("fromValue 反向解析与 getValue() 一致")
  void fromValueRoundTrips() {
    for (SourceId id : SourceId.values()) {
      assertThat(SourceId.fromValue(id.getValue())).isEqualTo(id);
    }
  }

  @Test
  @DisplayName("fromValue 对 null 抛出 NullPointerException")
  void fromValueRejectsNull() {
    assertThatThrownBy(() -> SourceId.fromValue(null)).isInstanceOf(NullPointerException.class);
  }

  @Test
  @DisplayName("fromValue 对未知值抛出 IllegalArgumentException")
  void fromValueRejectsUnknown() {
    assertThatThrownBy(() -> SourceId.fromValue("unknown_source"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("未知 SourceId");
  }
}
