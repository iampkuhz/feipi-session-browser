package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.ProjectStats;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 项目聚合统计行。
 *
 * <p>对应 Python {@code get_project_stats} 和 {@code list_projects} 查询结果。所有计数字段非负， 由 SQL {@code COUNT}
 * 和 {@code COALESCE(SUM(...), 0)} 保证。
 *
 * @param projectKey 项目键
 * @param projectName 项目显示名称
 * @param totalSessions 会话总数
 * @param claudeSessions claude_code agent 会话数
 * @param codexSessions codex agent 会话数
 * @param qoderSessions qoder agent 会话数
 * @param firstSeen 首次活动时间（ISO8601），空字符串表示未知
 * @param lastSeen 最近活动时间（ISO8601），空字符串表示未知
 * @param totalFreshInputTokens 非缓存输入 token 总量
 * @param totalOutputTokens 输出 token 总量
 * @param totalCacheReadTokens 缓存读取 token 总量
 * @param totalCacheWriteTokens 缓存写入 token 总量
 * @param totalTokens token 总量
 * @param totalToolCalls 工具调用总数
 * @param totalFailedTools 失败工具调用总数
 * @param totalUserMessages 用户消息总数
 * @param totalAssistantMessages 助手消息总数
 */
public record ProjectStatsRow(
    /* 项目键值。 */ String projectKey,
    /* 项目显示名称。 */ String projectName,
    /* 会话总数。 */ @PositiveOrZero long totalSessions,
    /* Claude 代理会话数量。 */ @PositiveOrZero long claudeSessions,
    /* Codex 代理会话数量。 */ @PositiveOrZero long codexSessions,
    /* Qoder 代理会话数量。 */ @PositiveOrZero long qoderSessions,
    /* 首次活动时间（ISO8601），空字符串表示未知。 */ String firstSeen,
    /* 最近活动时间（ISO8601），空字符串表示未知。 */ String lastSeen,
    /* 非缓存输入 令牌总数量。 */ @PositiveOrZero long totalFreshInputTokens,
    /* 输出 令牌总数量。 */ @PositiveOrZero long totalOutputTokens,
    /* 缓存读取 令牌总数量。 */ @PositiveOrZero long totalCacheReadTokens,
    /* 缓存写入 令牌总数量。 */ @PositiveOrZero long totalCacheWriteTokens,
    /* 令牌总数量。 */ @PositiveOrZero long totalTokens,
    /* 工具调用总数。 */ @PositiveOrZero long totalToolCalls,
    /* 失败工具调用总数。 */ @PositiveOrZero long totalFailedTools,
    /* 用户消息总数。 */ @PositiveOrZero long totalUserMessages,
    /* 助手消息总数。 */ @PositiveOrZero long totalAssistantMessages)
    implements ProjectStats {

  /**
   * 紧凑构造器，校验 record component 约束并应用默认值。
   *
   * <p>字符串 null 转为空字符串；计数和 token 字段由 {@link ValidationSupport} 校验非负。
   */
  public ProjectStatsRow {
    ValidationSupport.validateCanonicalConstructor(
        ProjectStatsRow.class,
        projectKey,
        projectName,
        totalSessions,
        claudeSessions,
        codexSessions,
        qoderSessions,
        firstSeen,
        lastSeen,
        totalFreshInputTokens,
        totalOutputTokens,
        totalCacheReadTokens,
        totalCacheWriteTokens,
        totalTokens,
        totalToolCalls,
        totalFailedTools,
        totalUserMessages,
        totalAssistantMessages);
    projectKey = projectKey == null ? "" : projectKey;
    projectName = projectName == null ? "" : projectName;
    firstSeen = firstSeen == null ? "" : firstSeen;
    lastSeen = lastSeen == null ? "" : lastSeen;
  }
}
