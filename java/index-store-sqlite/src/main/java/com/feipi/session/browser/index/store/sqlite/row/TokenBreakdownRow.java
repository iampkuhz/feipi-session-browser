package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.TokenBreakdown;
import com.feipi.session.browser.common.validation.ParamChecks;

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
    long totalFailedTools) implements TokenBreakdown {

  /**
   * 紧凑构造器，验证非负不变量。
   *
   * @throws IllegalArgumentException 当任何字段为负数时
   */
  public TokenBreakdownRow {
    ParamChecks.nonNegative(totalFreshInput, "totalFreshInput");
    ParamChecks.nonNegative(totalOutput, "totalOutput");
    ParamChecks.nonNegative(totalCacheRead, "totalCacheRead");
    ParamChecks.nonNegative(totalCacheWrite, "totalCacheWrite");
    ParamChecks.nonNegative(totalToolCalls, "totalToolCalls");
    ParamChecks.nonNegative(totalFailedTools, "totalFailedTools");
  }
}
