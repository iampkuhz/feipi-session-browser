package com.feipi.session.browser.index.store.sqlite.util;

import com.feipi.session.browser.validation.Finite;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.Collections;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * SQLite adapter 保留的百分位数 facade。
 *
 * <p>实际计算逻辑委托给 {@link com.feipi.session.browser.query.api.PercentileCalculator}，避免 index API 与
 * SQLite store 各自复制同一套百分位算法。
 */
public final class PercentileCalculator {

  /** 最小有效样本数，低于此值使用回退阈值。 */
  public static final int MIN_ROWS =
      com.feipi.session.browser.query.api.PercentileCalculator.MIN_ROWS;

  /** 时长回退阈值（秒）。 */
  public static final double DURATION_WARNING_SECONDS =
      com.feipi.session.browser.query.api.PercentileCalculator.DURATION_WARNING_SECONDS;

  public static final double DURATION_CRITICAL_SECONDS =
      com.feipi.session.browser.query.api.PercentileCalculator.DURATION_CRITICAL_SECONDS;

  /** 工具调用数回退阈值。 */
  public static final long TOOL_CALL_WARNING_COUNT =
      com.feipi.session.browser.query.api.PercentileCalculator.TOOL_CALL_WARNING_COUNT;

  public static final long TOOL_CALL_CRITICAL_COUNT =
      com.feipi.session.browser.query.api.PercentileCalculator.TOOL_CALL_CRITICAL_COUNT;

  /** 缓存写入 token 回退阈值。 */
  public static final long CACHE_WRITE_WARNING_TOKENS =
      com.feipi.session.browser.query.api.PercentileCalculator.CACHE_WRITE_WARNING_TOKENS;

  public static final long CACHE_WRITE_CRITICAL_TOKENS =
      com.feipi.session.browser.query.api.PercentileCalculator.CACHE_WRITE_CRITICAL_TOKENS;

  /** 工具失败率阈值。 */
  public static final double FAILED_TOOL_WARNING_RATIO =
      com.feipi.session.browser.query.api.PercentileCalculator.FAILED_TOOL_WARNING_RATIO;

  public static final double FAILED_TOOL_CRITICAL_RATIO =
      com.feipi.session.browser.query.api.PercentileCalculator.FAILED_TOOL_CRITICAL_RATIO;

  private PercentileCalculator() {}

  /**
   * 计算单个百分位数值。
   *
   * @param values 数值 observations
   * @param percentile 百分位（0-100）
   * @return 插值后的百分位数值，空列表时返回 null
   */
  public static Double percentile(List<Double> values, double percentile) {
    return com.feipi.session.browser.query.api.PercentileCalculator.percentile(values, percentile);
  }

  /**
   * 计算 P90、P95 和样本数量。
   *
   * @param values 数值 observations
   * @return 包含 p90、p95 和 count 的 SQLite facade 结果
   */
  public static PercentileResult computePercentiles(List<Double> values) {
    com.feipi.session.browser.query.api.PercentileCalculator.PercentileResult result =
        com.feipi.session.browser.query.api.PercentileCalculator.computePercentiles(values);
    return new PercentileResult(result.p90(), result.p95(), result.count());
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
    return com.feipi.session.browser.query.api.PercentileCalculator.getFallbackThreshold(
        metric.toApi(), severity);
  }

  /**
   * 计算会话指标的回退阈值。
   *
   * @param durationValues 活跃时长值（秒）
   * @param toolCallValues 工具调用数值
   * @param cacheWriteValues 缓存写入 token 值
   * @return 每个指标的阈值映射
   */
  public static Map<MetricKey, Thresholds> computeSessionThresholds(
      List<Double> durationValues, List<Double> toolCallValues, List<Double> cacheWriteValues) {
    Map<
            com.feipi.session.browser.query.api.PercentileCalculator.MetricKey,
            com.feipi.session.browser.query.api.PercentileCalculator.Thresholds>
        computed =
            com.feipi.session.browser.query.api.PercentileCalculator.computeSessionThresholds(
                durationValues, toolCallValues, cacheWriteValues);
    Map<MetricKey, Thresholds> result = new EnumMap<>(MetricKey.class);
    for (MetricKey metric : MetricKey.values()) {
      com.feipi.session.browser.query.api.PercentileCalculator.Thresholds thresholds =
          computed.get(metric.toApi());
      if (thresholds != null) {
        result.put(metric, Thresholds.fromApi(thresholds));
      }
    }
    return Collections.unmodifiableMap(result);
  }

  /** 指标键枚举。 */
  public enum MetricKey {
    /** 活跃持续时长秒数。 */
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
      return toApi().fallbackThresholds();
    }

    private com.feipi.session.browser.query.api.PercentileCalculator.MetricKey toApi() {
      return com.feipi.session.browser.query.api.PercentileCalculator.MetricKey.valueOf(name());
    }
  }

  /**
   * 百分位数计算结果。
   *
   * @param p90 P90 值，空列表时为 null
   * @param p95 P95 值，空列表时为 null
   * @param count 样本数
   */
  public record PercentileResult(
      /* P90 值，空列表时为 null。 */ Double p90,
      /* P95 值，空列表时为 null。 */ Double p95,
      /* 样本数量。 */ @PositiveOrZero int count) {

    /** 紧凑构造器，校验 record component 约束。 */
    public PercentileResult {
      ValidationSupport.validateCanonicalConstructor(PercentileResult.class, p90, p95, count);
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
      /* 警告阈值。 */ @Finite @PositiveOrZero double warning,
      /* 严重阈值。 */ @Finite @PositiveOrZero double critical,
      /* P90 值，可能为 null。 */ Double p90,
      /* P95 值，可能为 null。 */ Double p95,
      /* 用于计算的样本数量。 */ @PositiveOrZero int sampleCount) {

    /** 紧凑构造器，校验 record component 约束。 */
    public Thresholds {
      ValidationSupport.validateCanonicalConstructor(
          Thresholds.class, warning, critical, p90, p95, sampleCount);
    }

    private static Thresholds fromApi(
        com.feipi.session.browser.query.api.PercentileCalculator.Thresholds source) {
      Objects.requireNonNull(source, "source 不得为 null");
      return new Thresholds(
          source.warning(), source.critical(), source.p90(), source.p95(), source.sampleCount());
    }
  }
}
