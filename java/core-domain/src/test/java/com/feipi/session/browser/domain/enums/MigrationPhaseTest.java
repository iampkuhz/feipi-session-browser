package com.feipi.session.browser.domain.enums;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNullPointerException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * MigrationPhase 枚举单元测试。
 *
 * <p>验证四态枚举的值映射、默认值、fromValue 守卫和非法值处理。
 */
@DisplayName("MigrationPhase 枚举测试")
class MigrationPhaseTest {

  @Nested
  @DisplayName("外部协议值")
  class ExternalValues {

    @Test
    @DisplayName("OFF 对应 'off'")
    void offValue() {
      assertThat(MigrationPhase.OFF.getValue()).isEqualTo("off");
    }

    @Test
    @DisplayName("SHADOW 对应 'shadow'")
    void shadowValue() {
      assertThat(MigrationPhase.SHADOW.getValue()).isEqualTo("shadow");
    }

    @Test
    @DisplayName("ASSIST 对应 'assist'")
    void assistValue() {
      assertThat(MigrationPhase.ASSIST.getValue()).isEqualTo("assist");
    }

    @Test
    @DisplayName("ENFORCE 对应 'enforce'")
    void enforceValue() {
      assertThat(MigrationPhase.ENFORCE.getValue()).isEqualTo("enforce");
    }

    @Test
    @DisplayName("恰好四个枚举值")
    void exactlyFourValues() {
      assertThat(MigrationPhase.values()).hasSize(4);
    }
  }

  @Nested
  @DisplayName("默认值")
  class DefaultValue {

    @Test
    @DisplayName("DEFAULT 常量等于 OFF")
    void defaultIsOff() {
      assertThat(MigrationPhase.DEFAULT).isEqualTo(MigrationPhase.OFF);
    }
  }

  @Nested
  @DisplayName("fromValue 守卫 — 合法值")
  class FromValueValid {

    @Test
    @DisplayName("'off' 解析为 OFF")
    void offParses() {
      assertThat(MigrationPhase.fromValue("off")).isEqualTo(MigrationPhase.OFF);
    }

    @Test
    @DisplayName("'shadow' 解析为 SHADOW")
    void shadowParses() {
      assertThat(MigrationPhase.fromValue("shadow")).isEqualTo(MigrationPhase.SHADOW);
    }

    @Test
    @DisplayName("'assist' 解析为 ASSIST")
    void assistParses() {
      assertThat(MigrationPhase.fromValue("assist")).isEqualTo(MigrationPhase.ASSIST);
    }

    @Test
    @DisplayName("'enforce' 解析为 ENFORCE")
    void enforceParses() {
      assertThat(MigrationPhase.fromValue("enforce")).isEqualTo(MigrationPhase.ENFORCE);
    }

    @Test
    @DisplayName("大写 'OFF' 解析为 OFF（大小写不敏感）")
    void upperCaseOff() {
      assertThat(MigrationPhase.fromValue("OFF")).isEqualTo(MigrationPhase.OFF);
    }

    @Test
    @DisplayName("混合大小写 'Assist' 解析为 ASSIST")
    void mixedCaseAssist() {
      assertThat(MigrationPhase.fromValue("Assist")).isEqualTo(MigrationPhase.ASSIST);
    }

    @Test
    @DisplayName("前后空白 ' Off ' 自动修剪后解析为 OFF")
    void trimmedOff() {
      assertThat(MigrationPhase.fromValue(" Off ")).isEqualTo(MigrationPhase.OFF);
    }
  }

  @Nested
  @DisplayName("fromValue 守卫 — 非法值")
  class FromValueInvalid {

    @Test
    @DisplayName("空字符串抛出 IllegalArgumentException")
    void emptyStringThrows() {
      assertThatThrownBy(() -> MigrationPhase.fromValue(""))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值")
          .hasMessageContaining("允许值: off, shadow, assist, enforce");
    }

    @Test
    @DisplayName("'invalid' 抛出 IllegalArgumentException")
    void invalidThrows() {
      assertThatThrownBy(() -> MigrationPhase.fromValue("invalid"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'on' 抛出 IllegalArgumentException")
    void onThrows() {
      assertThatThrownBy(() -> MigrationPhase.fromValue("on"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'active' 抛出 IllegalArgumentException")
    void activeThrows() {
      assertThatThrownBy(() -> MigrationPhase.fromValue("active"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'disabled' 抛出 IllegalArgumentException")
    void disabledThrows() {
      assertThatThrownBy(() -> MigrationPhase.fromValue("disabled"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'SHADOWX' 抛出 IllegalArgumentException")
    void shadowxThrows() {
      assertThatThrownBy(() -> MigrationPhase.fromValue("SHADOWX"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("null 值抛出 NullPointerException")
    void nullValueThrows() {
      assertThatNullPointerException().isThrownBy(() -> MigrationPhase.fromValue(null));
    }
  }
}
