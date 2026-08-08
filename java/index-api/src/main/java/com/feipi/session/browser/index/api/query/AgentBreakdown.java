package com.feipi.session.browser.index.api.query;

/** dashboard 中按 agent 聚合的统计行。 */
public interface AgentBreakdown {
  /** 返回 agent 标识。 */
  String agent();

  /** 返回会话总数。 */
  long sessionCount();

  /** 返回最后活跃时间戳。 */
  String lastActive();

  /** 返回 token 总量。 */
  long totalTokens();

  /** 返回非缓存输入 token 总量。 */
  long freshInputTokens();

  /** 返回缓存读取 token 总量。 */
  long cacheReadTokens();

  /** 返回缓存写入 token 总量。 */
  long cacheWriteTokens();

  /** 返回输出 token 总量。 */
  long outputTokens();

  /** 返回工具调用总数。 */
  long totalToolCalls();

  /** 返回失败工具调用总数。 */
  long totalFailedTools();

  /** 返回用户消息总数。 */
  long totalUserMessages();

  /** 返回去重项目数。 */
  long projectCount();
}
