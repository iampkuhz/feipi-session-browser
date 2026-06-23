package com.feipi.session.browser.index.sqlite;

/**
 * Token 分类统计。
 *
 * <p>对应 Python {@code get_token_breakdown} 查询结果。所有字段由 {@code COALESCE(SUM(...), 0)} 保证非负，空表返回全零。
 *
 * @param totalFreshInput 非缓存输入 token 总量
 * @param totalOutput 输出 token 总量
 * @param totalCacheRead 缓存读取 token 总量
 * @param totalCacheWrite 缓存写入 token 总量
 * @param totalToolCalls 工具调用总数
 * @param totalFailedTools 失败工具调用总数
 */
public record TokenBreakdownRow(
    long totalFreshInput,
    long totalOutput,
    long totalCacheRead,
    long totalCacheWrite,
    long totalToolCalls,
    long totalFailedTools) {

  /**
   * 紧凑构造器，验证非负不变量。
   *
   * @throws IllegalArgumentException 当任何字段为负数时
   */
  public TokenBreakdownRow {
    if (totalFreshInput < 0) {
      throw new IllegalArgumentException("totalFreshInput 必须非负; got " + totalFreshInput);
    }
    if (totalOutput < 0) {
      throw new IllegalArgumentException("totalOutput 必须非负; got " + totalOutput);
    }
    if (totalCacheRead < 0) {
      throw new IllegalArgumentException("totalCacheRead 必须非负; got " + totalCacheRead);
    }
    if (totalCacheWrite < 0) {
      throw new IllegalArgumentException("totalCacheWrite 必须非负; got " + totalCacheWrite);
    }
    if (totalToolCalls < 0) {
      throw new IllegalArgumentException("totalToolCalls 必须非负; got " + totalToolCalls);
    }
    if (totalFailedTools < 0) {
      throw new IllegalArgumentException("totalFailedTools 必须非负; got " + totalFailedTools);
    }
  }
}
