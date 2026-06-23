package com.feipi.session.browser.index.sqlite;

/**
 * Dashboard 全局聚合行。
 *
 * <p>对应 Python {@code get_dashboard_stats} 查询结果。包含会话、项目、token、工具和消息的总量。 支持可选 agent 范围过滤。
 *
 * @param totalSessions 会话总数
 * @param claudeSessions claude_code 会话数
 * @param codexSessions codex 会话数
 * @param qoderSessions qoder 会话数
 * @param projectCount 去重项目数
 * @param totalTokens token 总量
 * @param totalFreshInputTokens 非缓存输入 token 总量
 * @param totalCacheReadTokens 缓存读取 token 总量
 * @param totalCacheWriteTokens 缓存写入 token 总量
 * @param totalOutputTokens 输出 token 总量
 * @param totalToolCalls 工具调用总数
 * @param totalFailedTools 失败工具调用总数
 * @param totalUserMessages 用户消息总数
 * @param totalAssistantMessages 助手消息总数
 */
public record DashboardRow(
    long totalSessions,
    long claudeSessions,
    long codexSessions,
    long qoderSessions,
    long projectCount,
    long totalTokens,
    long totalFreshInputTokens,
    long totalCacheReadTokens,
    long totalCacheWriteTokens,
    long totalOutputTokens,
    long totalToolCalls,
    long totalFailedTools,
    long totalUserMessages,
    long totalAssistantMessages) {}
