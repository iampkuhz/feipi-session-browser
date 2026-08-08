package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的 dashboard 聚合统计。 */
public interface DashboardStats {
  /** 返回会话总数。 */
  long totalSessions();

  /** 返回 Claude Code 会话数。 */
  long claudeSessions();

  /** 返回 Codex 会话数。 */
  long codexSessions();

  /** 返回 Qoder 会话数。 */
  long qoderSessions();

  /** 返回去重项目数。 */
  long projectCount();

  /** 返回 token 总量。 */
  long totalTokens();

  /** 返回非缓存输入 token 总量。 */
  long totalFreshInputTokens();

  /** 返回缓存读取 token 总量。 */
  long totalCacheReadTokens();

  /** 返回缓存写入 token 总量。 */
  long totalCacheWriteTokens();

  /** 返回输出 token 总量。 */
  long totalOutputTokens();

  /** 返回工具调用总数。 */
  long totalToolCalls();

  /** 返回失败工具调用总数。 */
  long totalFailedTools();

  /** 返回用户消息总数。 */
  long totalUserMessages();

  /** 返回助手消息总数。 */
  long totalAssistantMessages();
}
