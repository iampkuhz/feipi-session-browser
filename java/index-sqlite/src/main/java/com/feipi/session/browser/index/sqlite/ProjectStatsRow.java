package com.feipi.session.browser.index.sqlite;

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
    String projectKey,
    String projectName,
    long totalSessions,
    long claudeSessions,
    long codexSessions,
    long qoderSessions,
    String firstSeen,
    String lastSeen,
    long totalFreshInputTokens,
    long totalOutputTokens,
    long totalCacheReadTokens,
    long totalCacheWriteTokens,
    long totalTokens,
    long totalToolCalls,
    long totalFailedTools,
    long totalUserMessages,
    long totalAssistantMessages) {

  /**
   * 紧凑构造器，验证不变量。
   *
   * <p>字符串 null 转为空字符串；计数和 token 字段验证非负。
   */
  public ProjectStatsRow {
    projectKey = projectKey == null ? "" : projectKey;
    projectName = projectName == null ? "" : projectName;
    firstSeen = firstSeen == null ? "" : firstSeen;
    lastSeen = lastSeen == null ? "" : lastSeen;

    if (totalSessions < 0) {
      throw new IllegalArgumentException("totalSessions 必须非负; got " + totalSessions);
    }
    if (totalToolCalls < 0) {
      throw new IllegalArgumentException("totalToolCalls 必须非负; got " + totalToolCalls);
    }
    if (totalTokens < 0) {
      throw new IllegalArgumentException("totalTokens 必须非负; got " + totalTokens);
    }
  }
}
