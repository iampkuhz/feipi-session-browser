package com.feipi.session.browser.index.api.query;

/** dashboard 派生聚合指标。 */
public interface AggregateMetrics {
  long inputSideTotal();

  long totalRounds();

  Double cacheReuseRatio();

  Double cacheWriteRatio();

  Double outputRatio();

  Double toolsPerRound();

  Double tokensPerRound();
}
