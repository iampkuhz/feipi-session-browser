package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.DashboardStats;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;

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
    /* 会话总数。 */ @PositiveOrZero long totalSessions,
    /* Claude 会话数量。 */ @PositiveOrZero long claudeSessions,
    /* Codex 会话数量。 */ @PositiveOrZero long codexSessions,
    /* Qoder 会话数量。 */ @PositiveOrZero long qoderSessions,
    /* 去重项目数。 */ @PositiveOrZero long projectCount,
    /* 令牌总数量。 */ @PositiveOrZero long totalTokens,
    /* 非缓存输入 令牌总数量。 */ @PositiveOrZero long totalFreshInputTokens,
    /* 缓存读取 令牌总数量。 */ @PositiveOrZero long totalCacheReadTokens,
    /* 缓存写入 令牌总数量。 */ @PositiveOrZero long totalCacheWriteTokens,
    /* 输出 令牌总数量。 */ @PositiveOrZero long totalOutputTokens,
    /* 工具调用总数。 */ @PositiveOrZero long totalToolCalls,
    /* 失败工具调用总数。 */ @PositiveOrZero long totalFailedTools,
    /* 用户消息总数。 */ @PositiveOrZero long totalUserMessages,
    /* 助手消息总数。 */ @PositiveOrZero long totalAssistantMessages)
    implements DashboardStats {

  /** 紧凑构造器，校验 record component 约束。 */
  public DashboardRow {
    ValidationSupport.validateCanonicalConstructor(
        DashboardRow.class,
        totalSessions,
        claudeSessions,
        codexSessions,
        qoderSessions,
        projectCount,
        totalTokens,
        totalFreshInputTokens,
        totalCacheReadTokens,
        totalCacheWriteTokens,
        totalOutputTokens,
        totalToolCalls,
        totalFailedTools,
        totalUserMessages,
        totalAssistantMessages);
  }
}
