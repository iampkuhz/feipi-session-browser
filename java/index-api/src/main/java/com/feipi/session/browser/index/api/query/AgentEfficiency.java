package com.feipi.session.browser.index.api.query;

/** agent 与 model 维度的效率指标。 */
public interface AgentEfficiency {
  String agent();

  String model();

  long sessionCount();

  double avgDuration();

  double p95Duration();

  long avgTotalTokens();

  double avgTools();

  Double toolsPerRound();

  Double cacheReuseRatio();

  Double failedPerSession();
}
