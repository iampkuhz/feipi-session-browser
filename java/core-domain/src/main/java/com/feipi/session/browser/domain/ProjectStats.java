package com.feipi.session.browser.domain;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 项目级聚合统计信息。
 *
 * <p>汇总一个项目下所有会话的关键指标，包括会话数量、token 消耗、 工具调用次数和用户/助手消息计数。该类型被索引查询层消费， 用于项目列表展示和仪表板统计面板。
 *
 * @param projectKey 项目唯一标识键
 * @param projectName 项目显示名称
 * @param totalSessions 会话总数
 * @param claudeSessions Claude 会话数量
 * @param codexSessions Codex 会话数量
 * @param qoderSessions Qoder 会话数量
 * @param firstSeen 项目首次出现的时间戳（ISO 8601 格式）
 * @param lastSeen 项目最近出现的时间戳（ISO 8601 格式）
 * @param totalFreshInputTokens 所有会话的非缓存输入 token 总和
 * @param totalOutputTokens 所有会话的输出 token 总和
 * @param totalCacheReadTokens 所有会话的缓存读取 token 总和
 * @param totalCacheWriteTokens 所有会话的缓存写入 token 总和
 * @param totalToolCalls 所有会话的工具调用总次数
 * @param totalUserMessages 所有会话的用户消息总数
 * @param totalAssistantMessages 所有会话的助手消息总数
 * @param totalFailedTools 所有会话的失败工具调用总数
 */
@DomainModel
public record ProjectStats(
    @CoreField String projectKey,
    @CoreField String projectName,
    @CoreField long totalSessions,
    long claudeSessions,
    long codexSessions,
    long qoderSessions,
    @CoreField String firstSeen,
    @CoreField String lastSeen,
    long totalFreshInputTokens,
    long totalOutputTokens,
    long totalCacheReadTokens,
    long totalCacheWriteTokens,
    long totalToolCalls,
    long totalUserMessages,
    long totalAssistantMessages,
    long totalFailedTools) {

  /**
   * 创建全零的默认项目统计实例。
   *
   * @param key 项目唯一标识键
   * @param name 项目显示名称
   * @return 所有统计计数为零的默认实例
   */
  public static ProjectStats empty(String key, String name) {
    return new ProjectStats(key, name, 0, 0, 0, 0, "", "", 0, 0, 0, 0, 0, 0, 0, 0);
  }
}
