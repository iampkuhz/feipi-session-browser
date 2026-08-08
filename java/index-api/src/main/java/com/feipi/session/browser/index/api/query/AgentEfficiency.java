package com.feipi.session.browser.index.api.query;

/** agent 与 model 维度的效率指标。 */
public interface AgentEfficiency {
  /** 返回 agent 标识。 */
  String agent();

  /** 返回模型名称。 */
  String model();

  /** 返回会话数。 */
  long sessionCount();

  /** 返回平均会话时长，单位为秒。 */
  double avgDuration();

  /** 返回近似 P95 会话时长，单位为秒。 */
  double p95Duration();

  /** 返回每个会话的平均 token 总量。 */
  long avgTotalTokens();

  /** 返回每个会话的平均工具调用数。 */
  double avgTools();

  /** 返回每轮工具调用数；无可计算数据时返回 {@code null}。 */
  Double toolsPerRound();

  /** 返回缓存复用比率；无可计算数据时返回 {@code null}。 */
  Double cacheReuseRatio();

  /** 返回每个会话的失败工具调用数；无可计算数据时返回 {@code null}。 */
  Double failedPerSession();
}
