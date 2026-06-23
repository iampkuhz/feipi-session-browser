package com.feipi.session.browser.index.sqlite;

import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 百分位数计算与回退阈值。
 *
 * <p>提供 P90/P95 计算和静态回退阈值表，供异常检测器在数据不足时使用。 与 Python 端 {@code percentiles.py} 对应。
 *
 * <p>回退阈值用于数据量不足或分布偏斜时的异常检测。
 */
public final class PercentileCalculator {

  /** 最小有效样本数，低于此值使用回退阈值。 */
  public static final int MIN_ROWS = 20;

  /** 时长回退阈值（秒）。 */
  public static final double DURATION_WARNING_SECONDS = 3600.0;

  public static final double DURATION_CRITICAL_SECONDS = 7200.0;

  /** 工具调用数回退阈值。 */
  public static final long TOOL_CALL_WARNING_COUNT = 200;

  public static final long TOOL_CALL_CRITICAL_COUNT = 500;

  /** 缓存写入 token 回退阈值。 */
  public static final long CACHE_WRITE_WARNING_TOKENS = 200_000;

  public static final long CACHE_WRITE_CRITICAL_TOKENS = 500_000;

  /** 工具失败率阈值。 */
  public static final double FAILED_TOOL_WARNING_RATIO = 0.15;

  public static final double FAILED_TOOL_CRITICAL_RATIO = 0.25;

  private PercentileCalculator() {}

  /**
   * 计算单个百分位数值。
   *
   * <p>使用线性插值法。空列表返回 null。
   *
   * @param values 数值 observations
   * @param percentile 百分位（0-100）
   * @return 插值后的百分位数值，空列表时返回 null
   */
  public static Double percentile(List<Double> values, double percentile) {
    Objects.requireNonNull(values, "values 不得为 null");
    if (values.isEmpty()) {
      return null;
    }
    List<Double> sorted = new ArrayList<>(values);
    Collections.sort(sorted);
    int n = sorted.size();
    if (n == 1) {
      return sorted.get(0);
    }
    double k = (percentile / 100.0) * (n - 1);
    int floor = (int) k;
    int ceil = floor + 1;
    if (ceil >= n) {
      return sorted.get(n - 1);
    }
    double fraction = k - floor;
    return sorted.get(floor) + fraction * (sorted.get(ceil) - sorted.get(floor));
  }

  /**
   * 计算 P90、P95 和样本数。
   *
   * @param values 数值 observations
   * @return 包含 p90、p95 和 count 的结果
   */
  public static PercentileResult computePercentiles(List<Double> values) {
    Objects.requireNonNull(values, "values 不得为 null");
    return new PercentileResult(percentile(values, 90), percentile(values, 95), values.size());
  }

  /**
   * 获取指定指标和严重度的回退阈值。
   *
   * @param metric 指标名称
   * @param severity 严重度（"warning" 或 "critical"）
   * @return 回退阈值，未知指标/严重度时返回 null
   */
  public static Double getFallbackThreshold(MetricKey metric, String severity) {
    Objects.requireNonNull(metric, "metric 不得为 null");
    Objects.requireNonNull(severity, "severity 不得为 null");
    return metric.fallbackThresholds().get(severity);
  }

  /**
   * 计算会话指标的回退阈值。
   *
   * <p>当样本数 >= MIN_ROWS 且 P95 可用时使用 P95，否则使用静态回退值。
   *
   * @param durationValues 活跃时长值（秒）
   * @param toolCallValues 工具调用数值
   * @param cacheWriteValues 缓存写入 token 值
   * @return 每个指标的阈值映射
   */
  public static Map<MetricKey, Thresholds> computeSessionThresholds(
      List<Double> durationValues, List<Double> toolCallValues, List<Double> cacheWriteValues) {
    Objects.requireNonNull(durationValues, "durationValues 不得为 null");
    Objects.requireNonNull(toolCallValues, "toolCallValues 不得为 null");
    Objects.requireNonNull(cacheWriteValues, "cacheWriteValues 不得为 null");

    Map<MetricKey, Thresholds> result = new EnumMap<>(MetricKey.class);
    result.put(
        MetricKey.DURATION_SECONDS, computeThresholds(durationValues, MetricKey.DURATION_SECONDS));
    result.put(
        MetricKey.TOOL_CALL_COUNT, computeThresholds(toolCallValues, MetricKey.TOOL_CALL_COUNT));
    result.put(
        MetricKey.CACHE_WRITE_TOKENS,
        computeThresholds(cacheWriteValues, MetricKey.CACHE_WRITE_TOKENS));
    return Collections.unmodifiableMap(result);
  }

  private static Thresholds computeThresholds(List<Double> values, MetricKey metric) {
    PercentileResult pcts = computePercentiles(values);
    Map<String, Double> fallback = metric.fallbackThresholds();

    if (pcts.count() >= MIN_ROWS && pcts.p95() != null) {
      double warn = pcts.p95();
      double crit = pcts.p95() * 1.5;
      return new Thresholds(warn, crit, pcts.p90(), pcts.p95(), pcts.count());
    } else {
      double warn = fallback.getOrDefault("warning", 0.0);
      double crit = fallback.getOrDefault("critical", warn * 2);
      return new Thresholds(warn, crit, pcts.p90(), pcts.p95(), pcts.count());
    }
  }

  /** 指标键枚举。 */
  public enum MetricKey {
    /** 活跃时长（秒）。 */
    DURATION_SECONDS,
    /** 工具调用数。 */
    TOOL_CALL_COUNT,
    /** 缓存写入 token 数。 */
    CACHE_WRITE_TOKENS;

    /**
     * 获取该指标的回退阈值映射。
     *
     * @return 包含 "warning" 和 "critical" 键的不可变映射
     */
    public Map<String, Double> fallbackThresholds() {
      return switch (this) {
        case DURATION_SECONDS ->
            Map.of(
                "warning", DURATION_WARNING_SECONDS,
                "critical", DURATION_CRITICAL_SECONDS);
        case TOOL_CALL_COUNT ->
            Map.of(
                "warning", (double) TOOL_CALL_WARNING_COUNT,
                "critical", (double) TOOL_CALL_CRITICAL_COUNT);
        case CACHE_WRITE_TOKENS ->
            Map.of(
                "warning", (double) CACHE_WRITE_WARNING_TOKENS,
                "critical", (double) CACHE_WRITE_CRITICAL_TOKENS);
      };
    }
  }

  /**
   * 百分位数计算结果。
   *
   * @param p90 P90 值，空列表时为 null
   * @param p95 P95 值，空列表时为 null
   * @param count 样本数
   */
  public record PercentileResult(Double p90, Double p95, int count) {
    /**
     * 紧凑构造器，验证样本数非负。
     *
     * @throws IllegalArgumentException 当 count 为负数时
     */
    public PercentileResult {
      if (count < 0) {
        throw new IllegalArgumentException("count 必须非负; got " + count);
      }
    }
  }

  /**
   * 单个指标的阈值集合。
   *
   * @param warning 警告阈值
   * @param critical 严重阈值
   * @param p90 P90 值，可能为 null
   * @param p95 P95 值，可能为 null
   * @param sampleCount 用于计算的样本数
   */
  public record Thresholds(
      double warning, double critical, Double p90, Double p95, int sampleCount) {
    /**
     * 紧凑构造器，验证阈值和样本数。
     *
     * @throws IllegalArgumentException 当阈值或样本数为负数时
     */
    public Thresholds {
      if (warning < 0) {
        throw new IllegalArgumentException("warning 必须非负; got " + warning);
      }
      if (critical < 0) {
        throw new IllegalArgumentException("critical 必须非负; got " + critical);
      }
      if (sampleCount < 0) {
        throw new IllegalArgumentException("sampleCount 必须非负; got " + sampleCount);
      }
    }
  }
}
