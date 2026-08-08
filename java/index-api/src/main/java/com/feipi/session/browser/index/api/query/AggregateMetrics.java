package com.feipi.session.browser.index.api.query;

/** dashboard 派生聚合指标。 */
public interface AggregateMetrics {
  /** 返回输入侧 token 总量。 */
  long inputSideTotal();

  /** 返回助手消息总数。 */
  long totalRounds();

  /** 返回缓存读取占输入侧的比率；无可计算数据时返回 {@code null}。 */
  Double cacheReuseRatio();

  /** 返回缓存写入占输入侧的比率；无可计算数据时返回 {@code null}。 */
  Double cacheWriteRatio();

  /** 返回输出 token 占输入侧的比率；无可计算数据时返回 {@code null}。 */
  Double outputRatio();

  /** 返回每轮工具调用数；无可计算数据时返回 {@code null}。 */
  Double toolsPerRound();

  /** 返回每轮 token 消耗；无可计算数据时返回 {@code null}。 */
  Double tokensPerRound();
}
