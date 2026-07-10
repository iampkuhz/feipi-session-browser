package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.TokenBreakdown;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;

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
    /* 非缓存输入 令牌总数量。 */ @PositiveOrZero long totalFreshInput,
    /* 输出 令牌总数量。 */ @PositiveOrZero long totalOutput,
    /* 缓存读取 令牌总数量。 */ @PositiveOrZero long totalCacheRead,
    /* 缓存写入 令牌总数量。 */ @PositiveOrZero long totalCacheWrite,
    /* 工具调用总数。 */ @PositiveOrZero long totalToolCalls,
    /* 失败工具调用总数。 */ @PositiveOrZero long totalFailedTools)
    implements TokenBreakdown {

  /** 紧凑构造器，校验 record component 约束。 */
  public TokenBreakdownRow {
    ValidationSupport.validateCanonicalConstructor(
        TokenBreakdownRow.class,
        totalFreshInput,
        totalOutput,
        totalCacheRead,
        totalCacheWrite,
        totalToolCalls,
        totalFailedTools);
  }
}
