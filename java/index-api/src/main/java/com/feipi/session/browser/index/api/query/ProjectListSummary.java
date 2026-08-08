package com.feipi.session.browser.index.api.query;

/** 已过滤 project 列表的聚合总量。 */
public interface ProjectListSummary {
  /** 返回当前过滤条件下的项目数。 */
  long projectCount();

  /** 返回当前过滤条件下的会话数。 */
  long sessionCount();

  /** 返回非缓存输入 token 数。 */
  long freshInputTokens();

  /** 返回缓存读取 token 数。 */
  long cacheReadTokens();

  /** 返回缓存写入 token 数。 */
  long cacheWriteTokens();

  /** 返回输出 token 数。 */
  long outputTokens();

  /** 返回 token 总数。 */
  long totalTokens();

  /** 返回工具调用数。 */
  long toolCallCount();

  /** 返回失败工具调用数。 */
  long failedToolCount();
}
