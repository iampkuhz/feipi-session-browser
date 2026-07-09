package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的 project 聚合统计。 */
public interface ProjectStats {
  String projectKey();

  String projectName();

  long totalSessions();

  long claudeSessions();

  long codexSessions();

  long qoderSessions();

  String firstSeen();

  String lastSeen();

  long totalFreshInputTokens();

  long totalOutputTokens();

  long totalCacheReadTokens();

  long totalCacheWriteTokens();

  long totalTokens();

  long totalToolCalls();

  long totalFailedTools();

  long totalUserMessages();

  long totalAssistantMessages();
}
