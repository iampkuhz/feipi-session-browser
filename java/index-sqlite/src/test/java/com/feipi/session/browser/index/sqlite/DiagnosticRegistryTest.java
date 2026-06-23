package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.RoundSignalKey;
import com.feipi.session.browser.query.api.SessionAnomalyKey;
import com.feipi.session.browser.index.sqlite.DiagnosticRegistry.AnomalyDefinition;
import com.feipi.session.browser.index.sqlite.DiagnosticRegistry.SignalDefinition;
import java.util.EnumSet;
import java.util.Set;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 诊断注册表单元测试。
 *
 * <p>覆盖 {@link DiagnosticRegistry} 的会话异常和轮次信号定义查询。
 */
@DisplayName("诊断注册表测试")
class DiagnosticRegistryTest {

  @Nested
  @DisplayName("会话异常注册")
  class SessionAnomalyTests {

    @Test
    @DisplayName("sessionAnomalyKeys 返回所有已注册键")
    void sessionAnomalyKeysReturnsAll() {
      Set<SessionAnomalyKey> keys = DiagnosticRegistry.sessionAnomalyKeys();
      assertThat(keys)
          .containsExactlyInAnyOrder(
              SessionAnomalyKey.LONG_DURATION,
              SessionAnomalyKey.FAILED_RUN,
              SessionAnomalyKey.CACHE_WRITE_SPIKE);
    }

    @Test
    @DisplayName("sessionAnomaly 返回正确定义")
    void sessionAnomalyReturnsDefinition() {
      AnomalyDefinition def = DiagnosticRegistry.sessionAnomaly(SessionAnomalyKey.LONG_DURATION);
      assertThat(def).isNotNull();
      assertThat(def.key()).isEqualTo(SessionAnomalyKey.LONG_DURATION);
      assertThat(def.severityLevels())
          .containsExactlyInAnyOrder(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL);
    }

    @Test
    @DisplayName("CACHE_WRITE_SPIKE 支持 INFO 和 WARNING")
    void cacheWriteSpikeSupportsInfoAndWarning() {
      AnomalyDefinition def = DiagnosticRegistry.sessionAnomaly(SessionAnomalyKey.CACHE_WRITE_SPIKE);
      assertThat(def.severityLevels())
          .containsExactlyInAnyOrder(AnomalySeverity.INFO, AnomalySeverity.WARNING);
    }

    @Test
    @DisplayName("isKnownSessionAnomaly 检查注册状态")
    void isKnownSessionAnomalyChecksRegistration() {
      assertThat(DiagnosticRegistry.isKnownSessionAnomaly(SessionAnomalyKey.LONG_DURATION)).isTrue();
      assertThat(DiagnosticRegistry.isKnownSessionAnomaly(null)).isFalse();
    }

    @Test
    @DisplayName("定义不可变")
    void definitionsAreImmutable() {
      Set<SessionAnomalyKey> keys = DiagnosticRegistry.sessionAnomalyKeys();
      assertThatThrownBy(() -> keys.add(SessionAnomalyKey.LONG_DURATION))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }

  @Nested
  @DisplayName("轮次信号注册")
  class RoundSignalTests {

    @Test
    @DisplayName("roundSignalKeys 返回所有已注册键")
    void roundSignalKeysReturnsAll() {
      Set<RoundSignalKey> keys = DiagnosticRegistry.roundSignalKeys();
      assertThat(keys)
          .containsExactlyInAnyOrder(
              RoundSignalKey.FAILED_TOOL,
              RoundSignalKey.LLM_ERROR,
              RoundSignalKey.LONG_TOOL,
              RoundSignalKey.TOOL_BURST,
              RoundSignalKey.HIGH_WRITE,
              RoundSignalKey.LARGE_INPUT);
    }

    @Test
    @DisplayName("roundSignal 返回正确定义")
    void roundSignalReturnsDefinition() {
      SignalDefinition def = DiagnosticRegistry.roundSignal(RoundSignalKey.FAILED_TOOL);
      assertThat(def).isNotNull();
      assertThat(def.key()).isEqualTo(RoundSignalKey.FAILED_TOOL);
      assertThat(def.severityLevels())
          .containsExactlyInAnyOrder(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL);
    }

    @Test
    @DisplayName("LONG_TOOL 只支持 WARNING")
    void longToolOnlySupportsWarning() {
      SignalDefinition def = DiagnosticRegistry.roundSignal(RoundSignalKey.LONG_TOOL);
      assertThat(def.severityLevels()).containsExactly(AnomalySeverity.WARNING);
    }

    @Test
    @DisplayName("isKnownRoundSignal 检查注册状态")
    void isKnownRoundSignalChecksRegistration() {
      assertThat(DiagnosticRegistry.isKnownRoundSignal(RoundSignalKey.FAILED_TOOL)).isTrue();
      assertThat(DiagnosticRegistry.isKnownRoundSignal(null)).isFalse();
    }

    @Test
    @DisplayName("定义不可变")
    void definitionsAreImmutable() {
      Set<RoundSignalKey> keys = DiagnosticRegistry.roundSignalKeys();
      assertThatThrownBy(() -> keys.add(RoundSignalKey.FAILED_TOOL))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }

  @Nested
  @DisplayName("AnomalyDefinition record")
  class AnomalyDefinitionTests {

    @Test
    @DisplayName("supportsSeverity 检查严重度支持")
    void supportsSeverityChecksSupport() {
      AnomalyDefinition def =
          new AnomalyDefinition(
              SessionAnomalyKey.LONG_DURATION,
              EnumSet.of(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL));

      assertThat(def.supportsSeverity(AnomalySeverity.WARNING)).isTrue();
      assertThat(def.supportsSeverity(AnomalySeverity.CRITICAL)).isTrue();
      assertThat(def.supportsSeverity(AnomalySeverity.INFO)).isFalse();
    }

    @Test
    @DisplayName("空严重度集合抛出异常")
    void emptySeveritySetThrows() {
      assertThatThrownBy(
              () -> new AnomalyDefinition(SessionAnomalyKey.LONG_DURATION, EnumSet.noneOf(AnomalySeverity.class)))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("severityLevels 不得为空");
    }

    @Test
    @DisplayName("null key 抛出异常")
    void nullKeyThrows() {
      assertThatThrownBy(
              () -> new AnomalyDefinition(null, EnumSet.of(AnomalySeverity.WARNING)))
          .isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("SignalDefinition record")
  class SignalDefinitionTests {

    @Test
    @DisplayName("supportsSeverity 检查严重度支持")
    void supportsSeverityChecksSupport() {
      SignalDefinition def =
          new SignalDefinition(
              RoundSignalKey.LONG_TOOL,
              EnumSet.of(AnomalySeverity.WARNING));

      assertThat(def.supportsSeverity(AnomalySeverity.WARNING)).isTrue();
      assertThat(def.supportsSeverity(AnomalySeverity.CRITICAL)).isFalse();
    }

    @Test
    @DisplayName("不可变严重度集合")
    void immutableSeveritySet() {
      SignalDefinition def =
          new SignalDefinition(
              RoundSignalKey.LONG_TOOL,
              EnumSet.of(AnomalySeverity.WARNING));

      assertThatThrownBy(() -> def.severityLevels().add(AnomalySeverity.CRITICAL))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }
}
