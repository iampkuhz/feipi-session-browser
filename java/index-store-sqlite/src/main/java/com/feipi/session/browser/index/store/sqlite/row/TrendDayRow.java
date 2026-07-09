package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.TrendDay;
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
    String date,
    long claudeCount,
    long codexCount,
    long qoderCount,
    long claudeTokens,
    long codexTokens,
    long qoderTokens,
    long freshInputTokens,
    long cacheReadTokens,
    long cacheWriteTokens,
    long outputTokens,
    long totalTokens,
    long toolCalls,
    long failedTools,
    long totalCount,
    long claudeFreshInput,
    long claudeCacheRead,
    long claudeCacheWrite,
    long qoderFreshInput,
    long qoderCacheRead,
    long qoderCacheWrite,
    long codexFreshInput,
    long codexCacheRead,
    long codexCacheWrite) implements TrendDay {}
