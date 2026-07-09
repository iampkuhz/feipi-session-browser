package com.feipi.session.browser.index.api.query;

/** dashboard 中按 agent 聚合的统计行。 */
public interface AgentBreakdown {
  String agent();

  long sessionCount();

  String lastActive();

  long totalTokens();

  long freshInputTokens();

  long cacheReadTokens();

  long cacheWriteTokens();

  long outputTokens();

  long totalToolCalls();

  long totalFailedTools();

  long totalUserMessages();

  long projectCount();
}
