package com.feipi.session.browser.application;

import com.feipi.session.browser.index.sqlite.AnomalyDetector;
import com.feipi.session.browser.index.sqlite.DiagnosticRegistry;
import com.feipi.session.browser.index.sqlite.PercentileCalculator;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.AnomalyFilter;
import com.feipi.session.browser.query.api.AnomalyType;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.SessionAnomalyKey;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 诊断与异常检测 use case。
 *
 * <p>组合 {@link AnomalyDetector}、{@link DiagnosticRegistry} 和 {@link PercentileCalculator}，
 * 提供批量异常检测、过滤和阈值查询。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>异常定义和阈值由注册表和百分位计算器维护。
 *   <li>本 use case 信任已验证的 {@link SessionRow} 数据。
 * </ul>
 */
public final class DiagnosticsUseCase {

  /** 防止外部实例化，使用静态方法或构造器注入。 */
  public DiagnosticsUseCase() {}

  /**
   * 批量检测会话异常，支持过滤。
   *
   * @param rows 会话行列表
   * @param filter 异常过滤器，null 时不过滤
   * @return 过滤后的异常摘要列表，顺序与输入一致
   */
  public List<SessionAnomalySummary> detectWithFilter(List<SessionRow> rows, AnomalyFilter filter) {
    Objects.requireNonNull(rows, "rows 不得为 null");

    List<SessionAnomalySummary> all = AnomalyDetector.detectAll(rows);
    if (filter == null || filter.isUnfiltered()) {
      return all;
    }

    List<SessionAnomalySummary> filtered = new ArrayList<>();
    for (SessionAnomalySummary summary : all) {
      List<DetectedAnomaly> kept = new ArrayList<>();
      for (DetectedAnomaly anomaly : summary.anomalies()) {
        if (matchesFilter(anomaly, filter)) {
          kept.add(anomaly);
        }
      }
      if (!kept.isEmpty()) {
        filtered.add(
            new SessionAnomalySummary(summary.sessionKey(), Collections.unmodifiableList(kept)));
      } else {
        filtered.add(SessionAnomalySummary.empty(summary.sessionKey()));
      }
    }
    return Collections.unmodifiableList(filtered);
  }

  /**
   * 查询指定指标的阈值集合。
   *
   * @param durationValues 活跃时长值（秒）
   * @param toolCallValues 工具调用数值
   * @param cacheWriteValues 缓存写入 token 值
   * @return 每个指标的阈值映射
   */
  public Map<PercentileCalculator.MetricKey, PercentileCalculator.Thresholds> computeThresholds(
      List<Double> durationValues, List<Double> toolCallValues, List<Double> cacheWriteValues) {
    return PercentileCalculator.computeSessionThresholds(
        durationValues, toolCallValues, cacheWriteValues);
  }

  /**
   * 检查会话异常键是否已注册。
   *
   * @param key 异常键
   * @return 已注册时返回 true
   */
  public boolean isKnownAnomaly(SessionAnomalyKey key) {
    return DiagnosticRegistry.isKnownSessionAnomaly(key);
  }

  /** 检查异常是否匹配过滤器。 */
  private static boolean matchesFilter(DetectedAnomaly anomaly, AnomalyFilter filter) {
    // 类型过滤
    AnomalyType type = filter.type();
    return type == null || anomaly.type() == type;
  }
}
