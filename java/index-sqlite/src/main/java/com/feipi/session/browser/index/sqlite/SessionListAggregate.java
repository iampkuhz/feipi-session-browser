package com.feipi.session.browser.index.sqlite;

/**
 * 过滤后会话列表的聚合总量。
 *
 * <p>对应 Python {@code get_sessions_list_aggregate} 查询结果，用于会话列表头部展示。 所有字段非负，由 SQL {@code COUNT} 和
 * {@code COALESCE(SUM(...), 0)} 保证。
 *
 * @param sessionCount 符合过滤条件的会话总数
 * @param projectCount 符合过滤条件的去重项目数
 * @param totalTokens 符合过滤条件的 token 总量，无匹配行时为 0
 */
public record SessionListAggregate(long sessionCount, long projectCount, long totalTokens) {

  /**
   * 紧凑构造器，验证非负不变量。
   *
   * @throws IllegalArgumentException 当任何字段为负数时
   */
  public SessionListAggregate {
    if (sessionCount < 0) {
      throw new IllegalArgumentException("sessionCount 必须非负; got " + sessionCount);
    }
    if (projectCount < 0) {
      throw new IllegalArgumentException("projectCount 必须非负; got " + projectCount);
    }
    if (totalTokens < 0) {
      throw new IllegalArgumentException("totalTokens 必须非负; got " + totalTokens);
    }
  }
}
