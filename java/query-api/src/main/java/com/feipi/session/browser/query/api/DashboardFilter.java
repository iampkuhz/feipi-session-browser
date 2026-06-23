package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * Dashboard 过滤器。
 *
 * <p>控制 dashboard 视图的数据范围和聚合粒度。
 *
 * <p>默认值：
 *
 * <ul>
 *   <li>agent 范围：不过滤（匹配所有 agent）
 *   <li>分页：{@link PageRequest#DEFAULT}（offset=0, limit=50）
 * </ul>
 */
public final class DashboardFilter {

  private final AgentFilter agentFilter;
  private final PageRequest page;

  private DashboardFilter(AgentFilter agentFilter, PageRequest page) {
    this.agentFilter = agentFilter;
    this.page = page;
  }

  /**
   * 创建全默认值的 Dashboard 过滤器。
   *
   * @return 不过滤任何条件的默认实例
   */
  public static DashboardFilter defaults() {
    return new DashboardFilter(AgentFilter.NONE, PageRequest.DEFAULT);
  }

  /**
   * 基于当前过滤器创建新的实例，替换 agent 过滤器。
   *
   * @param agentFilter 新的 agent 过滤器
   * @return 新的 Dashboard 过滤器
   */
  public DashboardFilter withAgent(AgentFilter agentFilter) {
    Objects.requireNonNull(agentFilter, "agentFilter 不得为 null");
    return new DashboardFilter(agentFilter, page);
  }

  /**
   * 基于当前过滤器创建新的实例，替换分页请求。
   *
   * @param page 新的分页请求
   * @return 新的 Dashboard 过滤器
   */
  public DashboardFilter withPage(PageRequest page) {
    Objects.requireNonNull(page, "page 不得为 null");
    return new DashboardFilter(agentFilter, page);
  }

  /**
   * 获取 agent 过滤器。
   *
   * @return agent 过滤器
   */
  public AgentFilter agentFilter() {
    return agentFilter;
  }

  /**
   * 获取分页请求。
   *
   * @return 分页请求
   */
  public PageRequest page() {
    return page;
  }

  @Override
  public String toString() {
    return "DashboardFilter[" + agentFilter + ", " + page + "]";
  }
}
