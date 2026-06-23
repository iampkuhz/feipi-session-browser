package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 趋势查询过滤器。
 *
 * <p>控制趋势和活动查询的时间窗口和 agent 范围。
 *
 * <p>默认值：
 *
 * <ul>
 *   <li>时间窗口：最近 30 天
 *   <li>agent 范围：不过滤（匹配所有 agent）
 * </ul>
 *
 * <p>不可变值对象。通过 {@code withXxx} 方法创建替换字段的新实例。
 */
public final class TrendFilter {

  /** 默认时间窗口天数。 */
  public static final int DEFAULT_DAYS = 30;

  private final int days;
  private final AgentFilter agentFilter;

  private TrendFilter(int days, AgentFilter agentFilter) {
    this.days = days;
    this.agentFilter = agentFilter;
  }

  /**
   * 创建全默认值的趋势过滤器。
   *
   * @return 30 天、不过滤 agent 的默认实例
   */
  public static TrendFilter defaults() {
    return new TrendFilter(DEFAULT_DAYS, AgentFilter.NONE);
  }

  /**
   * 创建指定天数和默认 agent 过滤器的趋势过滤器。
   *
   * @param days 回溯天数，必须为正
   * @return 新的趋势过滤器
   * @throws IllegalArgumentException 当 days 非正时
   */
  public static TrendFilter ofDays(int days) {
    if (days < 1) {
      throw new IllegalArgumentException("days 必须为正; got " + days);
    }
    return new TrendFilter(days, AgentFilter.NONE);
  }

  /**
   * 基于当前过滤器创建新的实例，替换时间窗口。
   *
   * @param days 回溯天数，必须为正
   * @return 新的趋势过滤器
   * @throws IllegalArgumentException 当 days 非正时
   */
  public TrendFilter withDays(int days) {
    if (days < 1) {
      throw new IllegalArgumentException("days 必须为正; got " + days);
    }
    return new TrendFilter(days, agentFilter);
  }

  /**
   * 基于当前过滤器创建新的实例，替换 agent 过滤器。
   *
   * @param agentFilter 新的 agent 过滤器
   * @return 新的趋势过滤器
   */
  public TrendFilter withAgent(AgentFilter agentFilter) {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    return new TrendFilter(days, agentFilter);
  }

  /**
   * 获取回溯天数。
   *
   * @return 正整数天数
   */
  public int days() {
    return days;
  }

  /**
   * 获取 agent 过滤器。
   *
   * @return agent 过滤器
   */
  public AgentFilter agentFilter() {
    return agentFilter;
  }

  @Override
  public String toString() {
    return "TrendFilter[days=" + days + ", " + agentFilter + "]";
  }
}
