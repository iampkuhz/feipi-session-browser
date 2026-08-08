package com.feipi.session.browser.index.api.query;

/** 每日 token 与 session 趋势行。 */
public interface TrendDay {
  /** 返回按会话结束时间聚合的日期，格式为 {@code YYYY-MM-DD}。 */
  String date();

  /** 返回当天来自 Claude 的会话数。 */
  long claudeCount();

  /** 返回当天来自 Codex 的会话数。 */
  long codexCount();

  /** 返回当天来自 Qoder 的会话数。 */
  long qoderCount();

  /** 返回当天 Claude 会话消耗的全部 token 数。 */
  long claudeTokens();

  /** 返回当天 Codex 会话消耗的全部 token 数。 */
  long codexTokens();

  /** 返回当天 Qoder 会话消耗的全部 token 数。 */
  long qoderTokens();

  /** 返回当天所有会话消耗的新鲜输入 token 数。 */
  long freshInputTokens();

  /** 返回当天所有会话命中的缓存读取 token 数。 */
  long cacheReadTokens();

  /** 返回当天所有会话写入的缓存 token 数。 */
  long cacheWriteTokens();

  /** 返回当天所有会话生成的输出 token 数。 */
  long outputTokens();

  /** 返回当天所有会话消耗的全部 token 数。 */
  long totalTokens();

  /** 返回当天所有会话发起的工具调用数。 */
  long toolCalls();

  /** 返回当天所有会话中失败的工具调用数。 */
  long failedTools();

  /** 返回当天所有来源的会话总数。 */
  long totalCount();

  /** 返回当天 Claude 会话消耗的新鲜输入 token 数。 */
  long claudeFreshInput();

  /** 返回当天 Claude 会话命中的缓存读取 token 数。 */
  long claudeCacheRead();

  /** 返回当天 Claude 会话写入的缓存 token 数。 */
  long claudeCacheWrite();

  /** 返回当天 Qoder 会话消耗的新鲜输入 token 数。 */
  long qoderFreshInput();

  /** 返回当天 Qoder 会话命中的缓存读取 token 数。 */
  long qoderCacheRead();

  /** 返回当天 Qoder 会话写入的缓存 token 数。 */
  long qoderCacheWrite();

  /** 返回当天 Codex 会话消耗的新鲜输入 token 数。 */
  long codexFreshInput();

  /** 返回当天 Codex 会话命中的缓存读取 token 数。 */
  long codexCacheRead();

  /** 返回当天 Codex 会话写入的缓存 token 数。 */
  long codexCacheWrite();
}
