package com.feipi.session.browser.query.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 异常相关类型单元测试。
 *
 * <p>覆盖 {@link AnomalyType}、{@link AnomalySeverity}、{@link DetectedAnomaly}
 * 和 {@link SessionAnomalySummary} 的不变量和边界条件。
 */
@DisplayName("异常类型契约测试")
class AnomalyTypesTest {

  @Nested
  @DisplayName("AnomalyType")
  class AnomalyTypeTests {

    @Test
    @DisplayName("fromValue 返回正确枚举")
    void fromValueReturnsEnum() {
      assertThat(AnomalyType.fromValue("long_duration")).isEqualTo(AnomalyType.LONG_DURATION);
      assertThat(AnomalyType.fromValue("cache_write_spike")).isEqualTo(AnomalyType.CACHE_WRITE_SPIKE);
      assertThat(AnomalyType.fromValue("failed_run")).isEqualTo(AnomalyType.FAILED_RUN);
      assertThat(AnomalyType.fromValue("payload_visibility_mismatch"))
          .isEqualTo(AnomalyType.PAYLOAD_VISIBILITY_MISMATCH);
    }

    @Test
    @DisplayName("fromValue 未知值抛出异常")
    void fromValueUnknownThrows() {
      assertThatThrownBy(() -> AnomalyType.fromValue("unknown"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("无法识别的异常类型");
    }

    @Test
    @DisplayName("getValue 返回稳定协议值")
    void getValueReturnsStableValue() {
      assertThat(AnomalyType.LONG_DURATION.getValue()).isEqualTo("long_duration");
      assertThat(AnomalyType.FAILED_RUN.getValue()).isEqualTo("failed_run");
    }
  }

  @Nested
  @DisplayName("AnomalySeverity")
  class AnomalySeverityTests {

    @Test
    @DisplayName("fromValue 返回正确枚举")
    void fromValueReturnsEnum() {
      assertThat(AnomalySeverity.fromValue("critical")).isEqualTo(AnomalySeverity.CRITICAL);
      assertThat(AnomalySeverity.fromValue("warning")).isEqualTo(AnomalySeverity.WARNING);
      assertThat(AnomalySeverity.fromValue("info")).isEqualTo(AnomalySeverity.INFO);
    }

    @Test
    @DisplayName("fromValue 未知值抛出异常")
    void fromValueUnknownThrows() {
      assertThatThrownBy(() -> AnomalySeverity.fromValue("unknown"))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("无法识别的异常严重度");
    }

    @Test
    @DisplayName("comparePriority CRITICAL 优先于 WARNING")
    void comparePriorityCriticalBeforeWarning() {
      assertThat(AnomalySeverity.CRITICAL.comparePriority(AnomalySeverity.WARNING)).isLessThan(0);
    }

    @Test
    @DisplayName("comparePriority WARNING 优先于 INFO")
    void comparePriorityWarningBeforeInfo() {
      assertThat(AnomalySeverity.WARNING.comparePriority(AnomalySeverity.INFO)).isLessThan(0);
    }
  }

  @Nested
  @DisplayName("DetectedAnomaly")
  class DetectedAnomalyTests {

    @Test
    @DisplayName("factory 方法创建正确严重度")
    void factoryMethodsCreateCorrectSeverity() {
      assertThat(DetectedAnomaly.critical(AnomalyType.FAILED_RUN, "reason").severity())
          .isEqualTo(AnomalySeverity.CRITICAL);
      assertThat(DetectedAnomaly.warning(AnomalyType.LONG_DURATION, "reason").severity())
          .isEqualTo(AnomalySeverity.WARNING);
      assertThat(DetectedAnomaly.info(AnomalyType.CACHE_WRITE_SPIKE, "reason").severity())
          .isEqualTo(AnomalySeverity.INFO);
    }

    @Test
    @DisplayName("null type 抛出异常")
    void nullTypeThrows() {
      assertThatThrownBy(() -> new DetectedAnomaly(null, AnomalySeverity.WARNING, "reason"))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("null severity 抛出异常")
    void nullSeverityThrows() {
      assertThatThrownBy(() -> new DetectedAnomaly(AnomalyType.FAILED_RUN, null, "reason"))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("null reason 转换为空字符串")
    void nullReasonBecomesEmpty() {
      DetectedAnomaly anomaly = new DetectedAnomaly(AnomalyType.FAILED_RUN, AnomalySeverity.WARNING, null);
      assertThat(anomaly.reason()).isEmpty();
    }
  }

  @Nested
  @DisplayName("SessionAnomalySummary")
  class SessionAnomalySummaryTests {

    @Test
    @DisplayName("empty 创建空异常列表")
    void emptyCreatesEmptyList() {
      SessionAnomalySummary summary = SessionAnomalySummary.empty("key1");
      assertThat(summary.sessionKey()).isEqualTo("key1");
      assertThat(summary.anomalies()).isEmpty();
      assertThat(summary.anomalyCount()).isZero();
    }

    @Test
    @DisplayName("maxSeverity 空列表返回 INFO")
    void maxSeverityEmptyReturnsInfo() {
      SessionAnomalySummary summary = SessionAnomalySummary.empty("key1");
      assertThat(summary.maxSeverity()).isEqualTo(AnomalySeverity.INFO);
    }

    @Test
    @DisplayName("maxSeverity 返回最高严重度")
    void maxSeverityReturnsHighest() {
      SessionAnomalySummary summary =
          new SessionAnomalySummary(
              "key1",
              java.util.List.of(
                  DetectedAnomaly.info(AnomalyType.CACHE_WRITE_SPIKE, "info"),
                  DetectedAnomaly.critical(AnomalyType.FAILED_RUN, "critical")));
      assertThat(summary.maxSeverity()).isEqualTo(AnomalySeverity.CRITICAL);
    }

    @Test
    @DisplayName("mainReason 空列表返回空字符串")
    void mainReasonEmptyReturnsEmpty() {
      SessionAnomalySummary summary = SessionAnomalySummary.empty("key1");
      assertThat(summary.mainReason()).isEmpty();
    }

    @Test
    @DisplayName("mainReason 返回最高严重度异常的原因")
    void mainReasonReturnsHighestSeverityReason() {
      SessionAnomalySummary summary =
          new SessionAnomalySummary(
              "key1",
              java.util.List.of(
                  DetectedAnomaly.info(AnomalyType.CACHE_WRITE_SPIKE, "info reason"),
                  DetectedAnomaly.critical(AnomalyType.FAILED_RUN, "critical reason")));
      assertThat(summary.mainReason()).isEqualTo("critical reason");
    }

    @Test
    @DisplayName("hasType 检查异常类型存在")
    void hasTypeChecksPresence() {
      SessionAnomalySummary summary =
          new SessionAnomalySummary(
              "key1",
              java.util.List.of(DetectedAnomaly.warning(AnomalyType.LONG_DURATION, "reason")));
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isTrue();
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isFalse();
    }

    @Test
    @DisplayName("不可变列表防止修改")
    void immutableListPreventsModification() {
      SessionAnomalySummary summary =
          new SessionAnomalySummary(
              "key1",
              java.util.List.of(DetectedAnomaly.warning(AnomalyType.LONG_DURATION, "reason")));
      assertThatThrownBy(() -> summary.anomalies().add(DetectedAnomaly.info(AnomalyType.CACHE_WRITE_SPIKE, "x")))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }
}
