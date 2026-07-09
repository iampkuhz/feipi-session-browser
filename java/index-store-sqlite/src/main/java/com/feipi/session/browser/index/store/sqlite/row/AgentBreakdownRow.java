package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.AgentBreakdown;
/**
 * Per-agent 全量统计行。
 *
 * <p>对应 Python {@code list_agents} 查询结果。用于 All Agents 表格， 包含每个 agent 的会话数、token 细分、项目数、失败数、最后活跃时间等。
 *
 * @param agent agent 标识（claude_code / qoder / codex）
 * @param sessionCount 会话总数
 * @param lastActive 最后活跃时间戳
 * @param totalTokens token 总量（fresh + cache_read + cache_write + output）
 * @param freshInputTokens 非缓存输入 token 总量
 * @param cacheReadTokens 缓存读取 token 总量
 * @param cacheWriteTokens 缓存写入 token 总量
 * @param outputTokens 输出 token 总量
 * @param totalToolCalls 工具调用总数
 * @param totalFailedTools 失败工具调用总数
 * @param totalUserMessages 用户消息总数
 * @param projectCount 去重项目数
 */
public record AgentBreakdownRow(
    String agent,
    long sessionCount,
    String lastActive,
    long totalTokens,
    long freshInputTokens,
    long cacheReadTokens,
    long cacheWriteTokens,
    long outputTokens,
    long totalToolCalls,
    long totalFailedTools,
    long totalUserMessages,
    long projectCount) implements AgentBreakdown {}
