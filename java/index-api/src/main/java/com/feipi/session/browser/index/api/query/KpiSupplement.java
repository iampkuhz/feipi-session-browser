package com.feipi.session.browser.index.api.query;

/** dashboard 补充 KPI 聚合行。 */
public interface KpiSupplement {
  /** 返回最近 24 小时内有会话的去重项目数。 */
  long activeProjects24h();

  /** 返回最近 7 天内有会话的去重项目数。 */
  long activeProjects7d();

  /** 返回最近 7 天内首次出现的去重项目数。 */
  long newProjects7d();

  /** 返回 8 至 14 天前有会话的去重项目数。 */
  long activeProjectsPrevious7d();

  /** 返回今日开始的会话数。 */
  long todaySessions();

  /** 返回最近 7 天的每日平均会话数。 */
  double avgDailySessions7d();

  /** 返回会话时长中位数，单位为秒。 */
  double medianDurationSeconds();

  /** 返回输入三段均为 provider 上报且输入侧 token 大于零的会话数。 */
  long eligibleSessions();

  /** 返回符合条件会话的缓存读取比率中位数；不可计算时返回 {@code null}。 */
  Double p50CacheRatio();

  /** 返回缓存读取比率低于 20% 的符合条件会话数。 */
  long lowReadSessions();

  /** 返回至少发生一次工具调用失败的会话数。 */
  long affectedFailureSessions();

  /** 返回发生多次工具调用失败的会话数。 */
  long repeatedFailureSessions();

  /** 返回可验证起止时间的 wall 时长样本数，包含实测零。 */
  default long durationSampleCount() {
    return 0;
  }

  /** 返回四段 token 均由 provider 上报的完整样本数，包含实测零。 */
  default long tokenSampleCount() {
    return 0;
  }

  /** 返回显式内容测量且存在 normalized artifact 的样本数，包含观测到的零。 */
  default long contentSampleCount() {
    return 0;
  }

  /** 返回显式测量 user 消息数量的会话数，保留测量到的零。 */
  default long userMessageSampleCount() {
    return 0;
  }

  /** 返回显式测量 assistant 消息数量的会话数，保留测量到的零。 */
  default long assistantMessageSampleCount() {
    return 0;
  }

  /** 返回仅 user 消息测量样本的消息均值；没有样本时返回 null。 */
  default Double avgUserMessagesPerSession() {
    return null;
  }

  /** 返回仅 assistant 消息测量样本的消息均值；没有样本时返回 null。 */
  default Double avgAssistantMessagesPerSession() {
    return null;
  }
}
