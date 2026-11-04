package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.normalized.TokenProvenance;

/**
 * UTC 开始日 cohort 的新增会话与累计用量趋势行。
 *
 * <p>各项 token/tool 数为该日开始会话的整段累计量，不是逐 call 实际发生日的消费；未知或无效开始日期不参与。
 */
public interface TrendDay {
  /** 返回有效会话开始时间对应的 UTC 日期，格式为 {@code YYYY-MM-DD}。 */
  String date();

  /** 返回该日开始的 Claude 会话数。 */
  long claudeCount();

  /** 返回该日开始的 Codex 会话数。 */
  long codexCount();

  /** 返回该日开始的 Qoder 会话数。 */
  long qoderCount();

  /** 返回该日开始的 Claude 会话累计消耗的全部 token 数。 */
  long claudeTokens();

  /** 返回该日开始的 Codex 会话累计消耗的全部 token 数。 */
  long codexTokens();

  /** 返回该日开始的 Qoder 会话累计消耗的全部 token 数。 */
  long qoderTokens();

  /** 返回该日开始会话累计消耗的新鲜输入 token 数。 */
  long freshInputTokens();

  /** 返回该日开始会话累计命中的缓存读取 token 数。 */
  long cacheReadTokens();

  /** 返回该日开始会话累计写入的缓存 token 数。 */
  long cacheWriteTokens();

  /** 返回该日开始会话累计生成的输出 token 数。 */
  long outputTokens();

  /** 返回该日开始会话累计消耗的全部 token 数。 */
  long totalTokens();

  /** 返回该日开始会话累计发起的工具调用数。 */
  long toolCalls();

  /** 返回该日开始会话累计失败的工具调用数。 */
  long failedTools();

  /** 返回该日开始的所有来源会话总数。 */
  long totalCount();

  /** 返回该日开始的 Claude 会话累计消耗的新鲜输入 token 数。 */
  long claudeFreshInput();

  /** 返回该日开始的 Claude 会话累计命中的缓存读取 token 数。 */
  long claudeCacheRead();

  /** 返回该日开始的 Claude 会话累计写入的缓存 token 数。 */
  long claudeCacheWrite();

  /** 返回该日开始的 Qoder 会话累计消耗的新鲜输入 token 数。 */
  long qoderFreshInput();

  /** 返回该日开始的 Qoder 会话累计命中的缓存读取 token 数。 */
  long qoderCacheRead();

  /** 返回该日开始的 Qoder 会话累计写入的缓存 token 数。 */
  long qoderCacheWrite();

  /** 返回该日开始的 Codex 会话累计消耗的新鲜输入 token 数。 */
  long codexFreshInput();

  /** 返回该日开始的 Codex 会话累计命中的缓存读取 token 数。 */
  long codexCacheRead();

  /** 返回该日开始的 Codex 会话累计写入的缓存 token 数。 */
  long codexCacheWrite();

  /** 返回相同查询范围的四段计量来源；旧实现不推断为 provider 上报。 */
  default TokenProvenance tokenProvenance() {
    return TokenProvenance.unknown(totalCount());
  }
}
