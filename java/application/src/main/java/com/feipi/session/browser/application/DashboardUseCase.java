package com.feipi.session.browser.application;

import com.feipi.session.browser.index.api.query.DashboardQueryPort;
import com.feipi.session.browser.index.api.query.ActivityTrend;
import com.feipi.session.browser.index.api.query.AgentBreakdown;
import com.feipi.session.browser.index.api.query.AgentEfficiency;
import com.feipi.session.browser.index.api.query.AggregateMetrics;
import com.feipi.session.browser.index.api.query.DashboardStats;
import com.feipi.session.browser.index.api.query.KpiSupplement;
import com.feipi.session.browser.index.api.query.TokenBreakdown;
import com.feipi.session.browser.index.api.query.TrendDay;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Dashboard 聚合查询 use case。
 *
 * <p>组合 {@link DashboardQueryPort} 的 Dashboard 相关查询：全局统计、趋势、分布、效率指标。 支持可选缓存加速重复查询。
 *
 * <p>校验放置：过滤参数由 query-api 过滤器类型在入口验证，本 use case 信任已验证的 typed filter。
 */
public final class DashboardUseCase {

  private final DashboardQueryPort repository;
  private final QueryCache cache;
  private final int schemaVersion;

  /**
   * 创建 Dashboard use case。
   *
   * @param repository 聚合查询仓库
   * @param cache 可选缓存，null 时不缓存
   * @param schemaVersion 当前 schema 版本号
   */
  public DashboardUseCase(
      DashboardQueryPort repository,
      QueryCache cache,
      int schemaVersion) {
    this.repository = Objects.requireNonNull(repository, "repository 不得为 null");
    this.cache = cache;
    this.schemaVersion = schemaVersion;
  }

  /**
   * Dashboard 全局聚合统计。
   *
   * @param agentFilter agent 范围过滤器
   * @return Dashboard 聚合行
   */
  public DashboardStats stats(AgentFilter agentFilter) {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("stats", agentFilter);
      return cache.getOrLoad(
          "dashboardStats",
          paramsHash,
          schemaVersion,
          () -> repository.dashboardStats(agentFilter));
    }
    return repository.dashboardStats(agentFilter);
  }

  /**
   * Per-agent 全量统计，用于 All Agents 表格。
   *
   * @return 按 agent 分组的统计行列表
   */
  public List<AgentBreakdown> agentBreakdown() {
    if (cache != null) {
      return cache.getOrLoad(
          "agentBreakdown",
          0,
          schemaVersion,
          () -> repository.agentBreakdown());
    }
    return repository.agentBreakdown();
  }

  /**
   * Dashboard KPI 补充数据。
   *
   * @param agentFilter agent 范围过滤器
   * @return KPI 补充数据行
   */
  public KpiSupplement kpiSupplement(AgentFilter agentFilter) {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("kpiSupplement", agentFilter);
      return cache.getOrLoad(
          "kpiSupplement",
          paramsHash,
          schemaVersion,
          () -> repository.kpiSupplement(agentFilter));
    }
    return repository.kpiSupplement(agentFilter);
  }

  /**
   * 每日 token 和会话趋势数据。
   *
   * @param filter 趋势过滤器
   * @return 按日期升序排列的趋势行列表
   */
  public List<TrendDay> trendData(TrendFilter filter) {
    Objects.requireNonNull(filter, "filter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("trend", filter);
      return cache.getOrLoad(
          "trendData",
          paramsHash,
          schemaVersion,
          () -> repository.trendData(filter));
    }
    return repository.trendData(filter);
  }

  /**
   * 每日 prompt 活动趋势数据。
   *
   * @param filter 趋势过滤器
   * @return 按日期升序排列的活动趋势行列表
   */
  public List<ActivityTrend> activityTrend(TrendFilter filter) {
    Objects.requireNonNull(filter, "filter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("activity", filter);
      return cache.getOrLoad(
          "activityTrend",
          paramsHash,
          schemaVersion,
          () -> repository.activityTrend(filter));
    }
    return repository.activityTrend(filter);
  }

  /**
   * Token 分类统计。
   *
   * @return token 分类统计
   */
  public TokenBreakdown tokenBreakdown() {
    if (cache != null) {
      return cache.getOrLoad(
          "tokenBreakdown",
          0,
          schemaVersion,
          () -> repository.tokenBreakdown());
    }
    return repository.tokenBreakdown();
  }

  /**
   * 模型分布：每个非空模型的会话计数。
   *
   * @return 模型名称到会话计数的有序映射
   */
  public Map<String, Long> modelDistribution() {
    if (cache != null) {
      return cache.getOrLoad(
          "modelDist",
          0,
          schemaVersion,
          () -> repository.modelDistribution());
    }
    return repository.modelDistribution();
  }

  /**
   * Agent 分布：每个 agent 的会话计数。
   *
   * @return agent 标识到会话计数的有序映射
   */
  public Map<String, Long> agentDistribution() {
    if (cache != null) {
      return cache.getOrLoad(
          "agentDist",
          0,
          schemaVersion,
          () -> repository.agentDistribution());
    }
    return repository.agentDistribution();
  }

  /**
   * Dashboard 级聚合衍生指标。
   *
   * @return 聚合衍生指标行
   */
  public AggregateMetrics aggregateMetrics() {
    if (cache != null) {
      return cache.getOrLoad(
          "aggMetrics",
          0,
          schemaVersion,
          () -> repository.aggregateMetrics());
    }
    return repository.aggregateMetrics();
  }

  /**
   * Agent + model 分组效率指标。
   *
   * @return 按会话数降序排列的效率行列表
   */
  public List<AgentEfficiency> agentEfficiency() {
    if (cache != null) {
      return cache.getOrLoad(
          "agentEff",
          0,
          schemaVersion,
          () -> repository.agentEfficiency());
    }
    return repository.agentEfficiency();
  }
}
