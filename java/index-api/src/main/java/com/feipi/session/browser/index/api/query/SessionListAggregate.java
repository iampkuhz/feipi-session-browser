package com.feipi.session.browser.index.api.query;

/** 已过滤 session 列表的紧凑聚合总量。 */
public interface SessionListAggregate {
  /** 返回当前筛选条件命中的会话数。 */
  long sessionCount();

  /** 返回命中会话覆盖的项目数。 */
  long projectCount();

  /** 返回命中会话消耗的全部 token 总数。 */
  long totalTokens();
}
