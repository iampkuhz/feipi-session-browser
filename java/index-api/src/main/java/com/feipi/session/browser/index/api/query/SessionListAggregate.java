package com.feipi.session.browser.index.api.query;

/** 已过滤 session 列表的紧凑聚合总量。 */
public interface SessionListAggregate {
  long sessionCount();

  long projectCount();

  long totalTokens();
}
