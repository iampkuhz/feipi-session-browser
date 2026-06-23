package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.AnomalyType;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 异常检测器单元测试。
 *
 * <p>覆盖 {@link AnomalyDetector} 的工具失败率、活跃时长和缓存写入检测逻辑。
 * 包含边界值、零值和缺失值场景。
 */
@DisplayName("异常检测器测试")
class AnomalyDetectorTest {

  private static SessionRow createSessionRow(
      String sessionKey,
      long toolCallCount,
      long failedToolCount,
      double modelExecSeconds,
      double toolExecSeconds,
      long cacheWriteTokens) {
    return new SessionRow(
        sessionKey,
        "claude_code",
        "session-1",
        "title",
        "project-key",
        "project-name",
        "/cwd",
        "2024-01-01T00:00:00Z",
        "2024-01-01T01:00:00Z",
        3600.0,
        modelExecSeconds,
        toolExecSeconds,
        "claude-3",
        "main",
        "cli",
        10L,
        20L,
        toolCallCount,
        1000L,
        500L,
        200L,
        cacheWriteTokens,
        3700L,
        failedToolCount,
        0L,
        1000000.0,
        999999.0,
        "/path/to/file");
  }

  @Nested
  @DisplayName("工具失败率检测")
  class FailedRunTests {

    @Test
    @DisplayName("零工具调用不触发异常")
    void zeroToolCallsNoAnomaly() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isFalse();
    }

    @Test
    @DisplayName("零失败不触发异常")
    void zeroFailuresNoAnomaly() {
      SessionRow row = createSessionRow("key1", 100, 0, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isFalse();
    }

    @Test
    @DisplayName("失败率 10% 不触发异常")
    void tenPercentFailureNoAnomaly() {
      SessionRow row = createSessionRow("key1", 100, 10, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isFalse();
    }

    @Test
    @DisplayName("失败率 15% 触发 warning")
    void fifteenPercentFailureWarning() {
      SessionRow row = createSessionRow("key1", 100, 15, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.WARNING);
    }

    @Test
    @DisplayName("失败率 25% 触发 critical")
    void twentyFivePercentFailureCritical() {
      SessionRow row = createSessionRow("key1", 100, 25, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.CRITICAL);
    }

    @Test
    @DisplayName("失败率 50% 触发 critical")
    void fiftyPercentFailureCritical() {
      SessionRow row = createSessionRow("key1", 10, 5, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.CRITICAL);
    }
  }

  @Nested
  @DisplayName("活跃时长检测")
  class LongDurationTests {

    @Test
    @DisplayName("零活跃时长不触发异常")
    void zeroActiveTimeNoAnomaly() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isFalse();
    }

    @Test
    @DisplayName("活跃时长 30 分钟不触发异常")
    void thirtyMinutesNoAnomaly() {
      SessionRow row = createSessionRow("key1", 0, 0, 1200, 600, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isFalse();
    }

    @Test
    @DisplayName("活跃时长 1 小时触发 warning")
    void oneHourWarning() {
      SessionRow row = createSessionRow("key1", 0, 0, 2400, 1200, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isTrue();
      DetectedAnomaly anomaly = summary.anomalies().get(0);
      assertThat(anomaly.severity()).isEqualTo(AnomalySeverity.WARNING);
      assertThat(anomaly.reason()).contains("Active time");
    }

    @Test
    @DisplayName("活跃时长 2 小时触发 critical")
    void twoHoursCritical() {
      SessionRow row = createSessionRow("key1", 0, 0, 4800, 2400, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isTrue();
      DetectedAnomaly anomaly = summary.anomalies().get(0);
      assertThat(anomaly.severity()).isEqualTo(AnomalySeverity.CRITICAL);
    }

    @Test
    @DisplayName("活跃时长 3 小时触发 critical")
    void threeHoursCritical() {
      SessionRow row = createSessionRow("key1", 0, 0, 7200, 3600, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.CRITICAL);
    }
  }

  @Nested
  @DisplayName("缓存写入检测")
  class CacheWriteTests {

    @Test
    @DisplayName("零缓存写入不触发异常")
    void zeroCacheWriteNoAnomaly() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isFalse();
    }

    @Test
    @DisplayName("缓存写入 100K 不触发异常")
    void hundredKCacheWriteNoAnomaly() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 100_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isFalse();
    }

    @Test
    @DisplayName("缓存写入 200K 触发 info")
    void twoHundredKCacheWriteInfo() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 200_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isTrue();
      DetectedAnomaly anomaly = summary.anomalies().get(0);
      assertThat(anomaly.severity()).isEqualTo(AnomalySeverity.INFO);
    }

    @Test
    @DisplayName("缓存写入 500K 触发 warning")
    void fiveHundredKCacheWriteWarning() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 500_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isTrue();
      DetectedAnomaly anomaly = summary.anomalies().get(0);
      assertThat(anomaly.severity()).isEqualTo(AnomalySeverity.WARNING);
    }

    @Test
    @DisplayName("缓存写入 1M 触发 warning")
    void oneMCacheWriteWarning() {
      SessionRow row = createSessionRow("key1", 0, 0, 0, 0, 1_000_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.WARNING);
    }
  }

  @Nested
  @DisplayName("批量检测")
  class BatchDetectionTests {

    @Test
    @DisplayName("空列表返回空结果")
    void emptyListReturnsEmpty() {
      List<SessionAnomalySummary> results = AnomalyDetector.detectAll(Collections.emptyList());
      assertThat(results).isEmpty();
    }

    @Test
    @DisplayName("多个会话保持输入顺序")
    void multipleSessionsPreserveOrder() {
      SessionRow row1 = createSessionRow("key1", 100, 25, 0, 0, 0);
      SessionRow row2 = createSessionRow("key2", 0, 0, 0, 0, 0);
      SessionRow row3 = createSessionRow("key3", 0, 0, 7200, 3600, 0);

      List<SessionAnomalySummary> results = AnomalyDetector.detectAll(List.of(row1, row2, row3));

      assertThat(results).hasSize(3);
      assertThat(results.get(0).sessionKey()).isEqualTo("key1");
      assertThat(results.get(1).sessionKey()).isEqualTo("key2");
      assertThat(results.get(2).sessionKey()).isEqualTo("key3");
    }

    @Test
    @DisplayName("null rows 抛出异常")
    void nullRowsThrows() {
      assertThatThrownBy(() -> AnomalyDetector.detectAll(null))
          .isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("综合场景")
  class IntegrationTests {

    @Test
    @DisplayName("多个异常同时检测")
    void multipleAnomaliesDetected() {
      SessionRow row = createSessionRow("key1", 100, 30, 4800, 2400, 600_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);

      assertThat(summary.anomalyCount()).isEqualTo(3);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isTrue();
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isTrue();
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isTrue();
      assertThat(summary.maxSeverity()).isEqualTo(AnomalySeverity.CRITICAL);
    }

    @Test
    @DisplayName("无异常会话")
    void noAnomaliesCleanSession() {
      SessionRow row = createSessionRow("key1", 50, 2, 1800, 600, 50_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);

      assertThat(summary.anomalyCount()).isZero();
      assertThat(summary.maxSeverity()).isEqualTo(AnomalySeverity.INFO);
      assertThat(summary.mainReason()).isEmpty();
    }

    @Test
    @DisplayName("null row 抛出异常")
    void nullRowThrows() {
      assertThatThrownBy(() -> AnomalyDetector.detect(null))
          .isInstanceOf(NullPointerException.class);
    }
  }
}
