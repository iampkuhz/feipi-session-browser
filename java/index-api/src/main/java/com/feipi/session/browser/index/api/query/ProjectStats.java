package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的 project 聚合统计。 */
public interface ProjectStats {
  /** 返回项目的稳定唯一键。 */
  String projectKey();

  /** 返回项目的展示名称。 */
  String projectName();

  /** 返回项目包含的会话总数。 */
  long totalSessions();

  /** 返回来自 Claude 的会话数。 */
  long claudeSessions();

  /** 返回来自 Codex 的会话数。 */
  long codexSessions();

  /** 返回来自 Qoder 的会话数。 */
  long qoderSessions();

  /** 返回项目首次活动的 ISO8601 时间文本，未知时为空字符串。 */
  String firstSeen();

  /** 返回项目最近活动的 ISO8601 时间文本，未知时为空字符串。 */
  String lastSeen();

  /** 返回项目会话消耗的新鲜输入 token 总数。 */
  long totalFreshInputTokens();

  /** 返回项目会话生成的输出 token 总数。 */
  long totalOutputTokens();

  /** 返回项目会话命中的缓存读取 token 总数。 */
  long totalCacheReadTokens();

  /** 返回项目会话写入的缓存 token 总数。 */
  long totalCacheWriteTokens();

  /** 返回项目会话消耗的全部 token 总数。 */
  long totalTokens();

  /** 返回项目会话发起的工具调用总数。 */
  long totalToolCalls();

  /** 返回项目会话中失败的工具调用总数。 */
  long totalFailedTools();

  /** 返回项目会话中的用户消息总数。 */
  long totalUserMessages();

  /** 返回项目会话中的助手消息总数。 */
  long totalAssistantMessages();
}
