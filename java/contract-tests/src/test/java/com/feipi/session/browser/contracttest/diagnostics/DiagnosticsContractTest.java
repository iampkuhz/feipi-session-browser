package com.feipi.session.browser.contracttest.diagnostics;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.AnomalyDetector;
import com.feipi.session.browser.index.sqlite.DiagnosticRegistry;
import com.feipi.session.browser.index.sqlite.PercentileCalculator;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.AnomalyType;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.DiagnosticIssue;
import com.feipi.session.browser.query.api.DiagnosticIssueItem;
import com.feipi.session.browser.query.api.DiagnosticSeverity;
import com.feipi.session.browser.query.api.RoundSignalKey;
import com.feipi.session.browser.query.api.SessionAnomalyKey;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.query.api.SessionParseDiagnostics;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * 诊断、异常和百分位数契约测试。
 *
 * <p>验证跨模块的类型契约和边界语义，确保 query-api 类型定义与 index-sqlite 实现之间的一致性。
 */
@DisplayName("诊断契约测试")
class DiagnosticsContractTest {

  private static SessionRow createRow(
      String key, long tools, long failed, double modelExec, double toolExec, long cacheWrite) {
    return new SessionRow(
        key,
        "claude_code",
        "sid-1",
        "title",
        "proj",
        "project",
        "/cwd",
        "2024-01-01T00:00:00Z",
        "2024-01-01T01:00:00Z",
        3600.0,
        modelExec,
        toolExec,
        "claude-3",
        "main",
        "cli",
        10L,
        20L,
        tools,
        1000L,
        500L,
        200L,
        cacheWrite,
        3700L,
        failed,
        0L,
        1e6,
        999999.0,
        "/path");
  }

  @Nested
  @DisplayName("异常类型与注册表一致性")
  class AnomalyTypeConsistencyTests {

    @Test
    @DisplayName("所有注册键有对应 AnomalyType")
    void allRegisteredKeysHaveAnomalyType() {
      for (SessionAnomalyKey key : DiagnosticRegistry.sessionAnomalyKeys()) {
        AnomalyType.fromValue(key.getValue());
      }
    }

    @Test
    @DisplayName("注册表覆盖所有检测器使用的类型")
    void registryCoversDetectorTypes() {
      SessionRow failingRow = createRow("key1", 100, 30, 7200, 3600, 600_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(failingRow);

      for (DetectedAnomaly anomaly : summary.anomalies()) {
        SessionAnomalyKey key = SessionAnomalyKey.fromValue(anomaly.type().getValue());
        assertThat(DiagnosticRegistry.isKnownSessionAnomaly(key)).isTrue();
      }
    }

    @Test
    @DisplayName("注册表严重度与检测器输出一致")
    void registrySeverityMatchesDetectorOutput() {
      SessionRow row = createRow("key1", 100, 30, 7200, 3600, 600_000);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);

      for (DetectedAnomaly anomaly : summary.anomalies()) {
        SessionAnomalyKey key = SessionAnomalyKey.fromValue(anomaly.type().getValue());
        var def = DiagnosticRegistry.sessionAnomaly(key);
        assertThat(def.supportsSeverity(anomaly.severity())).isTrue();
      }
    }
  }

  @Nested
  @DisplayName("百分位数与阈值契约")
  class PercentileThresholdContractTests {

    @Test
    @DisplayName("回退阈值为正值")
    void fallbackThresholdsArePositive() {
      for (PercentileCalculator.MetricKey metric : PercentileCalculator.MetricKey.values()) {
        Double warning = PercentileCalculator.getFallbackThreshold(metric, "warning");
        Double critical = PercentileCalculator.getFallbackThreshold(metric, "critical");
        if (warning != null) {
          assertThat(warning).isGreaterThan(0);
        }
        if (critical != null) {
          assertThat(critical).isGreaterThan(0);
        }
      }
    }

    @Test
    @DisplayName("computeSessionThresholds 结果完整")
    void computeSessionThresholdsResultComplete() {
      Map<PercentileCalculator.MetricKey, PercentileCalculator.Thresholds> result =
          PercentileCalculator.computeSessionThresholds(
              List.of(1.0, 2.0), List.of(1.0, 2.0), List.of(1.0, 2.0));

      assertThat(result).containsKey(PercentileCalculator.MetricKey.DURATION_SECONDS);
      assertThat(result).containsKey(PercentileCalculator.MetricKey.TOOL_CALL_COUNT);
      assertThat(result).containsKey(PercentileCalculator.MetricKey.CACHE_WRITE_TOKENS);
    }

    @Test
    @DisplayName("MIN_ROWS 常量为正整数")
    void minRowsIsPositive() {
      assertThat(PercentileCalculator.MIN_ROWS).isGreaterThan(0);
    }
  }

  @Nested
  @DisplayName("解析诊断契约")
  class ParseDiagnosticsContractTests {

    @Test
    @DisplayName("DiagnosticIssue 枚举值与 Python 对齐")
    void diagnosticIssueValuesAlignedWithPython() {
      assertThat(DiagnosticIssue.BAD_JSON.getValue()).isEqualTo("BAD_JSON");
      assertThat(DiagnosticIssue.NON_OBJECT_SKIPPED.getValue()).isEqualTo("NON_OBJECT_SKIPPED");
      assertThat(DiagnosticIssue.FILE_NOT_FOUND.getValue()).isEqualTo("FILE_NOT_FOUND");
      assertThat(DiagnosticIssue.EMPTY_FILE.getValue()).isEqualTo("EMPTY_FILE");
      assertThat(DiagnosticIssue.MISSING_TIMESTAMP.getValue()).isEqualTo("MISSING_TIMESTAMP");
      assertThat(DiagnosticIssue.TOKEN_ESTIMATED.getValue()).isEqualTo("TOKEN_ESTIMATED");
    }

    @Test
    @DisplayName("SessionParseDiagnostics 计数一致性")
    void parseDiagnosticsCountsConsistent() {
      SessionParseDiagnostics diag =
          new SessionParseDiagnostics(
              "key1",
              "/path",
              100,
              50,
              10,
              List.of(
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.BAD_JSON, DiagnosticSeverity.CRITICAL, "err"),
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.TOKEN_ESTIMATED, DiagnosticSeverity.WARNING, "warn"),
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.TOKEN_ESTIMATED, DiagnosticSeverity.INFO, "inf")));

      assertThat(diag.criticalCount() + diag.warningCount() + diag.infoCount())
          .isEqualTo(diag.issues().size());
    }

    @Test
    @DisplayName("hasCritical/hasWarnings 与计数一致")
    void hasMethodsConsistentWithCounts() {
      SessionParseDiagnostics diag =
          new SessionParseDiagnostics(
              "key1",
              "/path",
              10,
              5,
              1,
              List.of(
                  DiagnosticIssueItem.fileLevel(
                      DiagnosticIssue.BAD_JSON, DiagnosticSeverity.CRITICAL, "err")));

      assertThat(diag.hasCritical()).isEqualTo(diag.criticalCount() > 0);
      assertThat(diag.hasWarnings()).isEqualTo(diag.warningCount() > 0);
    }
  }

  @Nested
  @DisplayName("轮次信号注册键契约")
  class RoundSignalKeyContractTests {

    @Test
    @DisplayName("所有轮次信号键有定义")
    void allRoundSignalKeysHaveDefinition() {
      for (RoundSignalKey key : RoundSignalKey.values()) {
        assertThat(DiagnosticRegistry.isKnownRoundSignal(key)).isTrue();
        assertThat(DiagnosticRegistry.roundSignal(key)).isNotNull();
      }
    }

    @Test
    @DisplayName("轮次信号键值与 Python 对齐")
    void roundSignalKeyValuesAlignedWithPython() {
      assertThat(RoundSignalKey.FAILED_TOOL.getValue()).isEqualTo("failed-tool");
      assertThat(RoundSignalKey.LLM_ERROR.getValue()).isEqualTo("llm-error");
      assertThat(RoundSignalKey.LONG_TOOL.getValue()).isEqualTo("long-tool");
      assertThat(RoundSignalKey.TOOL_BURST.getValue()).isEqualTo("tool-burst");
      assertThat(RoundSignalKey.HIGH_WRITE.getValue()).isEqualTo("high-write");
      assertThat(RoundSignalKey.LARGE_INPUT.getValue()).isEqualTo("large-input");
    }
  }

  @Nested
  @DisplayName("异常检测边界值")
  class AnomalyBoundaryTests {

    @Test
    @DisplayName("零值会话无异常")
    void zeroValueSessionNoAnomalies() {
      SessionRow row = createRow("key1", 0, 0, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.anomalyCount()).isZero();
      assertThat(summary.maxSeverity()).isEqualTo(AnomalySeverity.INFO);
    }

    @Test
    @DisplayName("空异常列表的 mainReason 为空")
    void emptyAnomalyListMainReasonEmpty() {
      SessionAnomalySummary summary = SessionAnomalySummary.empty("key1");
      assertThat(summary.mainReason()).isEmpty();
    }

    @Test
    @DisplayName("批量检测空列表")
    void batchDetectEmptyList() {
      List<SessionAnomalySummary> results = AnomalyDetector.detectAll(Collections.emptyList());
      assertThat(results).isEmpty();
    }

    @Test
    @DisplayName("边界值 14.99% 失败率不触发")
    void boundaryFourteenPercentNoTrigger() {
      SessionRow row = createRow("key1", 1000, 149, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isFalse();
    }

    @Test
    @DisplayName("边界值 15.0% 失败率触发 warning")
    void boundaryFifteenPercentWarning() {
      SessionRow row = createRow("key1", 1000, 150, 0, 0, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.FAILED_RUN)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.WARNING);
    }

    @Test
    @DisplayName("缓存写入 199999 不触发")
    void cacheWrite199999NoTrigger() {
      SessionRow row = createRow("key1", 0, 0, 0, 0, 199_999);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.CACHE_WRITE_SPIKE)).isFalse();
    }

    @Test
    @DisplayName("活跃时长 3599 秒不触发")
    void activeTime3599NoTrigger() {
      SessionRow row = createRow("key1", 0, 0, 2000, 1599, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isFalse();
    }

    @Test
    @DisplayName("活跃时长 3600 秒触发 warning")
    void activeTime3600Warning() {
      SessionRow row = createRow("key1", 0, 0, 2000, 1600, 0);
      SessionAnomalySummary summary = AnomalyDetector.detect(row);
      assertThat(summary.hasType(AnomalyType.LONG_DURATION)).isTrue();
      assertThat(summary.anomalies().get(0).severity()).isEqualTo(AnomalySeverity.WARNING);
    }
  }
}
