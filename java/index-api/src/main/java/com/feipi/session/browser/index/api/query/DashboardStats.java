package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的 dashboard 聚合统计。 */
public interface DashboardStats {
  long totalSessions();

  long claudeSessions();

  long codexSessions();

  long qoderSessions();

  long projectCount();

  long totalTokens();

  long totalFreshInputTokens();

  long totalCacheReadTokens();

  long totalCacheWriteTokens();

  long totalOutputTokens();

  long totalToolCalls();

  long totalFailedTools();

  long totalUserMessages();

  long totalAssistantMessages();
}
