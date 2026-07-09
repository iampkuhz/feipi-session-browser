package com.feipi.session.browser.index.api.query;

/** 已过滤 project 列表的聚合总量。 */
public interface ProjectListSummary {
  long projectCount();

  long sessionCount();

  long freshInputTokens();

  long cacheReadTokens();

  long cacheWriteTokens();

  long outputTokens();

  long totalTokens();

  long toolCallCount();

  long failedToolCount();
}
