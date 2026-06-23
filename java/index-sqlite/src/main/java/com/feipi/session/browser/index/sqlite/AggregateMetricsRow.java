package com.feipi.session.browser.index.sqlite;

/**
 * 聚合衍生指标行。
 *
 * <p>对应 Python {@code compute_aggregate_metrics} 查询结果。包含原始聚合总量和计算的衍生比率。
 *
 * <p>比率语义：
 *
 * <ul>
 *   <li>{@code cacheReuseRatio} — 缓存读取占输入侧比例
 *   <li>{@code cacheWriteRatio} — 缓存写入占输入侧比例
 *   <li>{@code outputRatio} — 输出 token 占输入侧比例
 *   <li>{@code toolsPerRound} — 平均每轮工具调用数
 *   <li>{@code tokensPerRound} — 平均每轮 token 消耗
 * </ul>
 *
 * <p>所有比率在分母为零或无数据时为 {@code null}。应通过 {@link #compute} 工厂方法创建， 工厂方法从原始 SQL 聚合值计算衍生比率。
 *
 * @param inputSideTotal 输入侧 token 总量（fresh + cache_read + cache_write）
 * @param totalRounds 助手消息总数
 * @param cacheReuseRatio 缓存复用比率，null 表示无数据
 * @param cacheWriteRatio 缓存写入比率，null 表示无数据
 * @param outputRatio 输出比率，null 表示无数据
 * @param toolsPerRound 每轮工具调用数，null 表示无数据
 * @param tokensPerRound 每轮 token 消耗，null 表示无数据
 */
public record AggregateMetricsRow(
    long inputSideTotal,
    long totalRounds,
    Double cacheReuseRatio,
    Double cacheWriteRatio,
    Double outputRatio,
    Double toolsPerRound,
    Double tokensPerRound) {

  /**
   * 紧凑构造器，验证非负不变量。
   *
   * <p>比率字段由 {@link #compute} 工厂方法计算并验证，此处仅校验总量字段。
   */
  public AggregateMetricsRow {
    if (inputSideTotal < 0) {
      throw new IllegalArgumentException("inputSideTotal 必须非负; got " + inputSideTotal);
    }
    if (totalRounds < 0) {
      throw new IllegalArgumentException("totalRounds 必须非负; got " + totalRounds);
    }
  }

  /**
   * 从原始聚合值创建聚合指标行。
   *
   * <p>计算衍生比率：缓存复用率、缓存写入率、输出率、每轮工具数和每轮 token 消耗。 零值分母产生 {@code null} 比率，与 Python {@code safe_div}
   * 行为一致。
   *
   * @param totalFreshInput 非缓存输入 token 总量
   * @param totalOutput 输出 token 总量
   * @param totalCacheRead 缓存读取 token 总量
   * @param totalCacheWrite 缓存写入 token 总量
   * @param totalTools 工具调用总数
   * @param totalRounds 助手消息总数
   * @return 计算好衍生比率的聚合指标行
   */
  public static AggregateMetricsRow compute(
      long totalFreshInput,
      long totalOutput,
      long totalCacheRead,
      long totalCacheWrite,
      long totalTools,
      long totalRounds) {
    long inputSide = totalFreshInput + totalCacheRead + totalCacheWrite;
    return new AggregateMetricsRow(
        inputSide,
        totalRounds,
        safeDivRound(totalCacheRead, inputSide, 4),
        safeDivRound(totalCacheWrite, inputSide, 4),
        safeDivRound(totalOutput, inputSide, 4),
        safeDivRound(totalTools, totalRounds, 2),
        safeDivRound(inputSide + totalOutput, totalRounds, 1));
  }

  /**
   * 安全除法并四舍五入。
   *
   * <p>分母为零或结果为零时返回 {@code null}，与 Python {@code safe_div} + falsy 检查一致。
   */
  static Double safeDivRound(long numerator, long denominator, int scale) {
    if (denominator <= 0) {
      return null;
    }
    double result = (double) numerator / denominator;
    if (result == 0.0) {
      return null;
    }
    return switch (scale) {
      case 1 -> Math.round(result * 10.0) / 10.0;
      case 2 -> Math.round(result * 100.0) / 100.0;
      case 4 -> Math.round(result * 10000.0) / 10000.0;
      default -> result;
    };
  }
}
