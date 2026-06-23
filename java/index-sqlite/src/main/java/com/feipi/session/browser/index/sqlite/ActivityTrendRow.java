package com.feipi.session.browser.index.sqlite;

/**
 * 每日活动趋势行。
 *
 * <p>对应 Python {@code get_prompt_activity_trend} 查询结果。按日历日分组，包含 prompt、助手轮次和工具调用计数。
 *
 * @param date 日期字符串（YYYY-MM-DD）
 * @param claudePrompts claude_code 当日用户 prompt 数
 * @param codexPrompts codex 当日用户 prompt 数
 * @param qoderPrompts qoder 当日用户 prompt 数
 * @param totalPrompts 当日用户 prompt 总数
 * @param assistantTurns 当日助手消息总数
 * @param toolCalls 当日工具调用总数
 */
public record ActivityTrendRow(
    String date,
    long claudePrompts,
    long codexPrompts,
    long qoderPrompts,
    long totalPrompts,
    long assistantTurns,
    long toolCalls) {}
