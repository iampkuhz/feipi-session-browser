package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.util.List;
import java.util.Map;

/** dashboard 聚合查询读取端口。 */
public interface DashboardQueryPort {

  /** 返回 agent 过滤条件下的 dashboard 总量。 */
  DashboardStats dashboardStats(AgentFilter agentFilter);

  /** 返回按 agent 拆分的 dashboard 明细行。 */
  List<AgentBreakdown> agentBreakdown();

  /** 返回 agent 过滤条件下的 dashboard KPI 补充数据。 */
  KpiSupplement kpiSupplement(AgentFilter agentFilter);

  /** 返回每日 token 与 session 趋势行。 */
  List<TrendDay> trendData(TrendFilter filter);

  /** 返回每日 prompt 活动趋势行。 */
  List<ActivityTrend> activityTrend(TrendFilter filter);

  /** 返回 token 分类总量。 */
  TokenBreakdown tokenBreakdown();

  /** 返回 model 分布计数。 */
  Map<String, Long> modelDistribution();

  /** 返回 agent 分布计数。 */
  Map<String, Long> agentDistribution();

  /** 返回 dashboard 派生聚合指标。 */
  AggregateMetrics aggregateMetrics();

  /** 返回 agent 与 model 效率行。 */
  List<AgentEfficiency> agentEfficiency();
}
