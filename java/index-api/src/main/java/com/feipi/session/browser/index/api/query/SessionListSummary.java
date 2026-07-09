package com.feipi.session.browser.index.api.query;

/** 已过滤 session 列表的聚合总量。 */
public interface SessionListSummary {
  long sessionCount();

  long projectCount();

  long freshInputTokens();

  long cacheReadTokens();

  long cacheWriteTokens();

  long outputTokens();

  long totalTokens();

  long failedToolCount();
}
