package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.normalized.TokenProvenance;

/** 已过滤 session 列表的聚合总量。 */
public interface SessionListSummary {
  /** 返回当前筛选条件命中的会话数。 */
  long sessionCount();

  /** 返回命中会话覆盖的项目数。 */
  long projectCount();

  /** 返回命中会话消耗的新鲜输入 token 总数。 */
  long freshInputTokens();

  /** 返回命中会话命中的缓存读取 token 总数。 */
  long cacheReadTokens();

  /** 返回命中会话写入的缓存 token 总数。 */
  long cacheWriteTokens();

  /** 返回命中会话生成的输出 token 总数。 */
  long outputTokens();

  /** 返回命中会话消耗的全部 token 总数。 */
  long totalTokens();

  /** 返回命中会话中失败的工具调用总数。 */
  long failedToolCount();

  /** 返回相同查询范围的四段计量来源；旧实现不推断为 provider 上报。 */
  default TokenProvenance tokenProvenance() {
    return TokenProvenance.unknown(sessionCount());
  }
}
