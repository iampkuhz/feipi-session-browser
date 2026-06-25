package com.feipi.session.browser.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNullPointerException;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.MigrationPhase;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * MigrationPhaseConfig 单元测试。
 *
 * <p>验证配置读取、环境变量解析、默认值回退和非法值 fail-fast 行为。
 */
@DisplayName("MigrationPhaseConfig 测试")
class MigrationPhaseConfigTest {

  @Nested
  @DisplayName("默认值语义")
  class DefaultSemantics {

    @Test
    @DisplayName("无环境变量时默认值为 OFF")
    void defaultIsOffWhenEnvAbsent() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> null);
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.OFF);
      assertThat(config.isOff()).isTrue();
      assertThat(config.isJavaFirstEnabled()).isFalse();
    }

    @Test
    @DisplayName("环境变量为空字符串时默认值为 OFF")
    void defaultIsOffWhenEnvEmpty() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> "");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.OFF);
    }

    @Test
    @DisplayName("环境变量为纯空白时默认值为 OFF")
    void defaultIsOffWhenEnvBlank() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> "   ");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.OFF);
    }

    @Test
    @DisplayName("resolve(null) 返回默认值 OFF")
    void resolveNullReturnsDefault() {
      MigrationPhaseConfig config = MigrationPhaseConfig.resolve(null);
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.OFF);
    }

    @Test
    @DisplayName("resolve(空字符串) 返回默认值 OFF")
    void resolveEmptyReturnsDefault() {
      MigrationPhaseConfig config = MigrationPhaseConfig.resolve("");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.OFF);
    }
  }

  @Nested
  @DisplayName("四态解析")
  class PhaseResolution {

    @Test
    @DisplayName("环境变量 'shadow' 解析为 SHADOW")
    void shadowFromEnv() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> "shadow");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.SHADOW);
      assertThat(config.isShadow()).isTrue();
      assertThat(config.isJavaFirstEnabled()).isTrue();
    }

    @Test
    @DisplayName("环境变量 'assist' 解析为 ASSIST")
    void assistFromEnv() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> "assist");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.ASSIST);
      assertThat(config.isAssist()).isTrue();
      assertThat(config.isJavaFirstEnabled()).isTrue();
    }

    @Test
    @DisplayName("环境变量 'enforce' 解析为 ENFORCE")
    void enforceFromEnv() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> "enforce");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.ENFORCE);
      assertThat(config.isEnforce()).isTrue();
      assertThat(config.isJavaFirstEnabled()).isTrue();
    }

    @Test
    @DisplayName("环境变量 'off' 解析为 OFF")
    void offFromEnv() {
      MigrationPhaseConfig config = MigrationPhaseConfig.fromEnvironment(name -> "off");
      assertThat(config.getPhase()).isEqualTo(MigrationPhase.OFF);
      assertThat(config.isOff()).isTrue();
      assertThat(config.isJavaFirstEnabled()).isFalse();
    }
  }

  @Nested
  @DisplayName("非法值 fail-fast")
  class InvalidValueFailFast {

    @Test
    @DisplayName("'invalid' 环境变量值抛出 IllegalArgumentException")
    void invalidEnvValueThrows() {
      assertThatThrownBy(() -> MigrationPhaseConfig.fromEnvironment(name -> "invalid"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'on' 环境变量值抛出 IllegalArgumentException")
    void onEnvValueThrows() {
      assertThatThrownBy(() -> MigrationPhaseConfig.fromEnvironment(name -> "on"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'active' 环境变量值抛出 IllegalArgumentException")
    void activeEnvValueThrows() {
      assertThatThrownBy(() -> MigrationPhaseConfig.fromEnvironment(name -> "active"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'SHADOWX' 环境变量值抛出 IllegalArgumentException")
    void shadowxEnvValueThrows() {
      assertThatThrownBy(() -> MigrationPhaseConfig.fromEnvironment(name -> "SHADOWX"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("'123' 环境变量值抛出 IllegalArgumentException")
    void numericEnvValueThrows() {
      assertThatThrownBy(() -> MigrationPhaseConfig.fromEnvironment(name -> "123"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }

    @Test
    @DisplayName("resolve 非法值抛出 IllegalArgumentException")
    void resolveInvalidThrows() {
      assertThatThrownBy(() -> MigrationPhaseConfig.resolve("bogus"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("非法的迁移阶段值");
    }
  }

  @Nested
  @DisplayName("构造器验证")
  class ConstructorValidation {

    @Test
    @DisplayName("phase 为 null 时抛出 NullPointerException")
    void nullPhaseThrows() {
      assertThatNullPointerException().isThrownBy(() -> new MigrationPhaseConfig(null));
    }

    @Test
    @DisplayName("fromEnvironment 的 provider 为 null 时抛出 NullPointerException")
    void nullProviderThrows() {
      assertThatNullPointerException().isThrownBy(() -> MigrationPhaseConfig.fromEnvironment(null));
    }
  }

  @Nested
  @DisplayName("便捷查询方法互斥性")
  class MutuallyExclusivePredicates {

    @Test
    @DisplayName("OFF 状态下只有 isOff 为 true")
    void offPredicates() {
      MigrationPhaseConfig config = new MigrationPhaseConfig(MigrationPhase.OFF);
      assertThat(config.isOff()).isTrue();
      assertThat(config.isShadow()).isFalse();
      assertThat(config.isAssist()).isFalse();
      assertThat(config.isEnforce()).isFalse();
    }

    @Test
    @DisplayName("SHADOW 状态下只有 isShadow 为 true")
    void shadowPredicates() {
      MigrationPhaseConfig config = new MigrationPhaseConfig(MigrationPhase.SHADOW);
      assertThat(config.isOff()).isFalse();
      assertThat(config.isShadow()).isTrue();
      assertThat(config.isAssist()).isFalse();
      assertThat(config.isEnforce()).isFalse();
    }

    @Test
    @DisplayName("ASSIST 状态下只有 isAssist 为 true")
    void assistPredicates() {
      MigrationPhaseConfig config = new MigrationPhaseConfig(MigrationPhase.ASSIST);
      assertThat(config.isOff()).isFalse();
      assertThat(config.isShadow()).isFalse();
      assertThat(config.isAssist()).isTrue();
      assertThat(config.isEnforce()).isFalse();
    }

    @Test
    @DisplayName("ENFORCE 状态下只有 isEnforce 为 true")
    void enforcePredicates() {
      MigrationPhaseConfig config = new MigrationPhaseConfig(MigrationPhase.ENFORCE);
      assertThat(config.isOff()).isFalse();
      assertThat(config.isShadow()).isFalse();
      assertThat(config.isAssist()).isFalse();
      assertThat(config.isEnforce()).isTrue();
    }
  }
}
