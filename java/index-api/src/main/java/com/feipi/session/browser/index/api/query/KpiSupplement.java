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

  /** 返回输入侧 token 大于零的会话数。 */
  long eligibleSessions();

  /** 返回符合条件会话的缓存读取比率中位数；不可计算时返回 {@code null}。 */
  Double p50CacheRatio();

  /** 返回缓存读取比率低于 20% 的符合条件会话数。 */
  long lowReadSessions();

  /** 返回至少发生一次工具调用失败的会话数。 */
  long affectedFailureSessions();

  /** 返回发生多次工具调用失败的会话数。 */
  long repeatedFailureSessions();
}
