package com.feipi.session.browser.application;

import com.feipi.session.browser.index.sqlite.ActivityTrendRow;
import com.feipi.session.browser.index.sqlite.AgentEfficiencyRow;
import com.feipi.session.browser.index.sqlite.AggregateMetricsRow;
import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.DashboardRow;
import com.feipi.session.browser.index.sqlite.TokenBreakdownRow;
import com.feipi.session.browser.index.sqlite.TrendDayRow;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Dashboard 聚合查询 use case。
 *
 * <p>组合 {@link AggregateQueryRepository} 的 Dashboard 相关查询：全局统计、趋势、分布、效率指标。 支持可选缓存加速重复查询。
 *
 * <p>校验放置：过滤参数由 query-api 过滤器类型在入口验证，本 use case 信任已验证的 typed filter。
 */
public final class DashboardUseCase {

  private final AggregateQueryRepository repository;
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
      AggregateQueryRepository repository, QueryCache cache, int schemaVersion) {
    this.repository = Objects.requireNonNull(repository, "repository 不得为 null");
    this.cache = cache;
    this.schemaVersion = schemaVersion;
  }

  /**
   * Dashboard 全局聚合统计。
   *
   * @param agentFilter agent 范围过滤器
   * @return Dashboard 聚合行
   * @throws SQLException 查询失败
   */
  public DashboardRow stats(AgentFilter agentFilter) throws SQLException {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("stats", agentFilter);
      return cache.getOrLoad(
          "dashboardStats",
          paramsHash,
          schemaVersion,
          () -> {
            try {
              return repository.dashboardStats(agentFilter);
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.dashboardStats(agentFilter);
  }

  /**
   * 每日 token 和会话趋势数据。
   *
   * @param filter 趋势过滤器
   * @return 按日期升序排列的趋势行列表
   * @throws SQLException 查询失败
   */
  public List<TrendDayRow> trendData(TrendFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("trend", filter);
      return cache.getOrLoad(
          "trendData",
          paramsHash,
          schemaVersion,
          () -> {
            try {
              return repository.trendData(filter);
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.trendData(filter);
  }

  /**
   * 每日 prompt 活动趋势数据。
   *
   * @param filter 趋势过滤器
   * @return 按日期升序排列的活动趋势行列表
   * @throws SQLException 查询失败
   */
  public List<ActivityTrendRow> activityTrend(TrendFilter filter) throws SQLException {
    Objects.requireNonNull(filter, "filter 不得为 null");
    if (cache != null) {
      int paramsHash = Objects.hash("activity", filter);
      return cache.getOrLoad(
          "activityTrend",
          paramsHash,
          schemaVersion,
          () -> {
            try {
              return repository.activityTrend(filter);
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.activityTrend(filter);
  }

  /**
   * Token 分类统计。
   *
   * @return token 分类统计
   * @throws SQLException 查询失败
   */
  public TokenBreakdownRow tokenBreakdown() throws SQLException {
    if (cache != null) {
      return cache.getOrLoad(
          "tokenBreakdown",
          0,
          schemaVersion,
          () -> {
            try {
              return repository.tokenBreakdown();
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.tokenBreakdown();
  }

  /**
   * 模型分布：每个非空模型的会话计数。
   *
   * @return 模型名称到会话计数的有序映射
   * @throws SQLException 查询失败
   */
  public Map<String, Long> modelDistribution() throws SQLException {
    if (cache != null) {
      return cache.getOrLoad(
          "modelDist",
          0,
          schemaVersion,
          () -> {
            try {
              return repository.modelDistribution();
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.modelDistribution();
  }

  /**
   * Agent 分布：每个 agent 的会话计数。
   *
   * @return agent 标识到会话计数的有序映射
   * @throws SQLException 查询失败
   */
  public Map<String, Long> agentDistribution() throws SQLException {
    if (cache != null) {
      return cache.getOrLoad(
          "agentDist",
          0,
          schemaVersion,
          () -> {
            try {
              return repository.agentDistribution();
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.agentDistribution();
  }

  /**
   * Dashboard 级聚合衍生指标。
   *
   * @return 聚合衍生指标行
   * @throws SQLException 查询失败
   */
  public AggregateMetricsRow aggregateMetrics() throws SQLException {
    if (cache != null) {
      return cache.getOrLoad(
          "aggMetrics",
          0,
          schemaVersion,
          () -> {
            try {
              return repository.aggregateMetrics();
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.aggregateMetrics();
  }

  /**
   * Agent + model 分组效率指标。
   *
   * @return 按会话数降序排列的效率行列表
   * @throws SQLException 查询失败
   */
  public List<AgentEfficiencyRow> agentEfficiency() throws SQLException {
    if (cache != null) {
      return cache.getOrLoad(
          "agentEff",
          0,
          schemaVersion,
          () -> {
            try {
              return repository.agentEfficiency();
            } catch (SQLException e) {
              throw new RuntimeException(e);
            }
          });
    }
    return repository.agentEfficiency();
  }
}
