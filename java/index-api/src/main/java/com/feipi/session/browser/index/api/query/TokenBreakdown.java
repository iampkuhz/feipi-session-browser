package com.feipi.session.browser.index.api.query;

/** token 分类总量。 */
public interface TokenBreakdown {
  long totalFreshInput();

  long totalOutput();

  long totalCacheRead();

  long totalCacheWrite();

  long totalToolCalls();

  long totalFailedTools();
}
