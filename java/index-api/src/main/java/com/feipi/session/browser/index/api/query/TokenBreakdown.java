package com.feipi.session.browser.index.api.query;

/** token 分类总量。 */
public interface TokenBreakdown {
  /** 返回新鲜输入 token 总数。 */
  long totalFreshInput();

  /** 返回输出 token 总数。 */
  long totalOutput();

  /** 返回缓存读取 token 总数。 */
  long totalCacheRead();

  /** 返回缓存写入 token 总数。 */
  long totalCacheWrite();

  /** 返回工具调用总数。 */
  long totalToolCalls();

  /** 返回失败的工具调用总数。 */
  long totalFailedTools();
}
