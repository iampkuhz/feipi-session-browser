package com.feipi.session.browser.index.sqlite;

/**
 * 每日趋势数据行。
 *
 * <p>对应 Python {@code get_trend_data} 查询结果。按日历日分组，包含 per-agent 会话计数和 token 分布。
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
    long totalCount) {}
