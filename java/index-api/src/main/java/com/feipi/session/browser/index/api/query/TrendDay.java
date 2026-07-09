package com.feipi.session.browser.index.api.query;

/** 每日 token 与 session 趋势行。 */
public interface TrendDay {
  String date();

  long claudeCount();

  long codexCount();

  long qoderCount();

  long claudeTokens();

  long codexTokens();

  long qoderTokens();

  long freshInputTokens();

  long cacheReadTokens();

  long cacheWriteTokens();

  long outputTokens();

  long totalTokens();

  long toolCalls();

  long failedTools();

  long totalCount();

  long claudeFreshInput();

  long claudeCacheRead();

  long claudeCacheWrite();

  long qoderFreshInput();

  long qoderCacheRead();

  long qoderCacheWrite();

  long codexFreshInput();

  long codexCacheRead();

  long codexCacheWrite();
}
