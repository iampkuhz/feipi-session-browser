package com.feipi.session.browser.index.sqlite;

/**
 * Agent 效率指标行。
 *
 * <p>对应 Python {@code compute_agent_efficiency} 查询结果。按 agent + model 分组，包含会话计数、时长统计、 token
 * 使用、工具效率和缓存复用率。P95 时长由 nearest-rank 近似计算。
 *
 * <p>比率语义与 {@link AggregateMetricsRow} 一致。零值分母产生 {@code null}。
 *
 * @param agent agent 标识
 * @param model 模型名称，{@code null} 或空 model 映射为 "unknown"
 * @param sessionCount 会话数
 * @param avgDuration 平均时长（秒），保留一位小数
 * @param p95Duration P95 时长（秒），nearest-rank 近似
 * @param avgInputSide 平均输入侧 token 总量
 * @param avgTools 平均每会话工具调用数，保留一位小数
 * @param toolsPerRound 每轮工具调用数，null 表示无数据
 * @param cacheReuseRatio 缓存复用比率，null 表示无数据
 * @param failedPerSession 每会话失败数，null 表示无数据
 */
public record AgentEfficiencyRow(
    String agent,
    String model,
    long sessionCount,
    double avgDuration,
    double p95Duration,
    long avgInputSide,
    double avgTools,
    Double toolsPerRound,
    Double cacheReuseRatio,
    Double failedPerSession) {

  /**
   * 紧凑构造器，验证会话计数非负并规范化空 model。
   *
   * @throws IllegalArgumentException 当 sessionCount 为负数时
   */
  public AgentEfficiencyRow {
    if (sessionCount < 0) {
      throw new IllegalArgumentException("sessionCount 必须非负; got " + sessionCount);
    }
    if (model == null || model.isEmpty()) {
      model = "unknown";
    }
  }
}
