package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.TrendDay;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 每日趋势数据行。
 *
 * <p>对应 Python {@code get_trend_data} 查询结果。按日历日分组，包含 per-agent 会话计数和 token 分布。 同时包含 per-agent 输入侧
 * cache 组件（fresh/cache read/cache write），供 Cache Health 多曲线使用。
 *
 * <p>时间语义：日期由 SQLite {@code DATE(ended_at)} 计算，空 ended_at 归入当天。
 *
 * @param date 日期字符串（YYYY-MM-DD）
 * @param claudeCount claude_code 当日会话数
 * @param codexCount codex 当日会话数
 * @param qoderCount qoder 当日会话数
 * @param claudeTokens claude_code 当日 token 总量
 * @param codexTokens codex 当日 token 总量
 * @param qoderTokens qoder 当日 token 总量
 * @param freshInputTokens 当日非缓存输入 token 总量
 * @param cacheReadTokens 当日缓存读取 token 总量
 * @param cacheWriteTokens 当日缓存写入 token 总量
 * @param outputTokens 当日输出 token 总量
 * @param totalTokens 当日 token 总量
 * @param toolCalls 当日工具调用总数
 * @param failedTools 当日失败工具调用总数
 * @param totalCount 当日会话总数
 * @param claudeFreshInput claude_code 当日 fresh input token
 * @param claudeCacheRead claude_code 当日 cache read token
 * @param claudeCacheWrite claude_code 当日 cache write token
 * @param qoderFreshInput qoder 当日 fresh input token
 * @param qoderCacheRead qoder 当日 cache read token
 * @param qoderCacheWrite qoder 当日 cache write token
 * @param codexFreshInput codex 当日 fresh input token
 * @param codexCacheRead codex 当日 cache read token
 * @param codexCacheWrite codex 当日 cache write token
 */
public record TrendDayRow(
    /* 日期字符串（YYYY-MM-DD）。 */ @NotBlank String date,
    /* claude_code 当日会话数量。 */ @PositiveOrZero long claudeCount,
    /* codex 当日会话数量。 */ @PositiveOrZero long codexCount,
    /* qoder 当日会话数量。 */ @PositiveOrZero long qoderCount,
    /* claude_code 当日 令牌总数量。 */ @PositiveOrZero long claudeTokens,
    /* codex 当日 令牌总数量。 */ @PositiveOrZero long codexTokens,
    /* qoder 当日 令牌总数量。 */ @PositiveOrZero long qoderTokens,
    /* 当日非缓存输入 令牌总数量。 */ @PositiveOrZero long freshInputTokens,
    /* 当日缓存读取 令牌总数量。 */ @PositiveOrZero long cacheReadTokens,
    /* 当日缓存写入 令牌总数量。 */ @PositiveOrZero long cacheWriteTokens,
    /* 当日输出 令牌总数量。 */ @PositiveOrZero long outputTokens,
    /* 当日 令牌总数量。 */ @PositiveOrZero long totalTokens,
    /* 当日工具调用总数。 */ @PositiveOrZero long toolCalls,
    /* 当日失败工具调用总数。 */ @PositiveOrZero long failedTools,
    /* 当日会话总数。 */ @PositiveOrZero long totalCount,
    /* Claude 当日新鲜输入令牌数量。 */ @PositiveOrZero long claudeFreshInput,
    /* Claude 当日缓存读取令牌数量。 */ @PositiveOrZero long claudeCacheRead,
    /* Claude 当日缓存写入令牌数量。 */ @PositiveOrZero long claudeCacheWrite,
    /* Qoder 当日新鲜输入令牌数量。 */ @PositiveOrZero long qoderFreshInput,
    /* Qoder 当日缓存读取令牌数量。 */ @PositiveOrZero long qoderCacheRead,
    /* Qoder 当日缓存写入令牌数量。 */ @PositiveOrZero long qoderCacheWrite,
    /* Codex 当日新鲜输入令牌数量。 */ @PositiveOrZero long codexFreshInput,
    /* Codex 当日缓存读取令牌数量。 */ @PositiveOrZero long codexCacheRead,
    /* Codex 当日缓存写入令牌数量。 */ @PositiveOrZero long codexCacheWrite)
    implements TrendDay {

  /** 紧凑构造器，校验 record component 约束。 */
  public TrendDayRow {
    ValidationSupport.validateCanonicalConstructor(
        TrendDayRow.class,
        date,
        claudeCount,
        codexCount,
        qoderCount,
        claudeTokens,
        codexTokens,
        qoderTokens,
        freshInputTokens,
        cacheReadTokens,
        cacheWriteTokens,
        outputTokens,
        totalTokens,
        toolCalls,
        failedTools,
        totalCount,
        claudeFreshInput,
        claudeCacheRead,
        claudeCacheWrite,
        qoderFreshInput,
        qoderCacheRead,
        qoderCacheWrite,
        codexFreshInput,
        codexCacheRead,
        codexCacheWrite);
  }
}
