package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.AnomalyType;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * 会话级异常检测器。
 *
 * <p>基于会话行数据检测异常。与 Python 端 {@code anomalies.py} 中
 * {@code detect_session_anomalies} 对应。
 *
 * <p>检测逻辑：
 *
 * <ul>
 *   <li>工具失败率：failed/toolCall >= 0.25 为 critical，>= 0.15 为 warning
 *   <li>活跃时长：model + tool execution >= 2h 为 critical，>= 1h 为 warning
 *   <li>缓存写入：cacheWrite >= 500K 为 warning，>= 200K 为 info
 * </ul>
 *
 * <p>阈值来自 {@link PercentileCalculator} 的静态回退值。
 */
public final class AnomalyDetector {

  private static final double SECONDS_PER_HOUR = 3600.0;

  private AnomalyDetector() {}

  /**
   * 检测单个会话的异常。
   *
   * @param row 会话行数据
   * @return 检测到的异常集合
   */
  public static SessionAnomalySummary detect(SessionRow row) {
    Objects.requireNonNull(row, "row 不得为 null");
    List<DetectedAnomaly> anomalies = new ArrayList<>();

    detectFailedRun(row, anomalies);
    detectLongDuration(row, anomalies);
    detectCacheWriteSpike(row, anomalies);

    return new SessionAnomalySummary(row.sessionKey(), Collections.unmodifiableList(anomalies));
  }

  /**
   * 批量检测会话异常。
   *
   * @param rows 会话行数据列表
   * @return 每个会话的异常检测结果列表，保持输入顺序
   */
  public static List<SessionAnomalySummary> detectAll(List<SessionRow> rows) {
    Objects.requireNonNull(rows, "rows 不得为 null");
    List<SessionAnomalySummary> results = new ArrayList<>(rows.size());
    for (SessionRow row : rows) {
      results.add(detect(row));
    }
    return Collections.unmodifiableList(results);
  }

  /**
   * 检测工具失败率异常。
   *
   * <p>仅在 failed > 0 且 toolCallCount > 0 时检测。失败率 >= 0.25 为 critical，>= 0.15 为 warning。
   */
  private static void detectFailedRun(SessionRow row, List<DetectedAnomaly> anomalies) {
    long failed = row.failedToolCount();
    long tools = row.toolCallCount();

    if (failed > 0 && tools > 0) {
      double failRatio = (double) failed / tools;
      if (failRatio >= PercentileCalculator.FAILED_TOOL_CRITICAL_RATIO) {
        int percent = (int) (failRatio * 100);
        anomalies.add(
            DetectedAnomaly.critical(
                AnomalyType.FAILED_RUN,
                failed + " failed tool call(s) (" + percent + "%)"));
      } else if (failRatio >= PercentileCalculator.FAILED_TOOL_WARNING_RATIO) {
        int percent = (int) (failRatio * 100);
        anomalies.add(
            DetectedAnomaly.warning(
                AnomalyType.FAILED_RUN,
                failed + " failed tool call(s) (" + percent + "%)"));
      }
    }
  }

  /**
   * 检测活跃时长异常。
   *
   * <p>活跃时长 = modelExecutionSeconds + toolExecutionSeconds。
   * >= 2h 为 critical，>= 1h 为 warning。
   */
  private static void detectLongDuration(SessionRow row, List<DetectedAnomaly> anomalies) {
    double modelExec = row.modelExecutionSeconds();
    double toolExec = row.toolExecutionSeconds();
    double activeTime = modelExec + toolExec;

    if (activeTime > 0) {
      double warnThreshold = PercentileCalculator.DURATION_WARNING_SECONDS;
      double critThreshold = PercentileCalculator.DURATION_CRITICAL_SECONDS;

      if (activeTime >= critThreshold) {
        double hours = activeTime / SECONDS_PER_HOUR;
        double modelHours = modelExec / SECONDS_PER_HOUR;
        double toolHours = toolExec / SECONDS_PER_HOUR;
        double critHours = critThreshold / SECONDS_PER_HOUR;
        anomalies.add(
            DetectedAnomaly.critical(
                AnomalyType.LONG_DURATION,
                String.format(
                    "Active time %.1fh (model %.1fh + tool %.1fh) exceeds critical threshold (%.1fh)",
                    hours, modelHours, toolHours, critHours)));
      } else if (activeTime >= warnThreshold) {
        double hours = activeTime / SECONDS_PER_HOUR;
        double modelHours = modelExec / SECONDS_PER_HOUR;
        double toolHours = toolExec / SECONDS_PER_HOUR;
        double warnHours = warnThreshold / SECONDS_PER_HOUR;
        anomalies.add(
            DetectedAnomaly.warning(
                AnomalyType.LONG_DURATION,
                String.format(
                    "Active time %.1fh (model %.1fh + tool %.1fh) exceeds warning threshold (%.1fh)",
                    hours, modelHours, toolHours, warnHours)));
      }
    }
  }

  /**
   * 检测缓存写入异常。
   *
   * <p>cacheWriteTokens >= 500K 为 warning，>= 200K 为 info。
   * 注意：缓存写入是可见性信号，不是失败指标，因此最高只到 warning。
   */
  private static void detectCacheWriteSpike(SessionRow row, List<DetectedAnomaly> anomalies) {
    long cacheWrite = row.cacheWriteTokens();
    long warnThreshold = PercentileCalculator.CACHE_WRITE_WARNING_TOKENS;
    long critThreshold = PercentileCalculator.CACHE_WRITE_CRITICAL_TOKENS;

    if (cacheWrite >= critThreshold) {
      anomalies.add(
          DetectedAnomaly.warning(
              AnomalyType.CACHE_WRITE_SPIKE,
              "Cache creation " + cacheWrite + " tokens exceeds threshold (" + critThreshold + ")"));
    } else if (cacheWrite >= warnThreshold) {
      anomalies.add(
          DetectedAnomaly.info(
              AnomalyType.CACHE_WRITE_SPIKE,
              "Cache creation " + cacheWrite + " tokens exceeds threshold (" + warnThreshold + ")"));
    }
  }
}
