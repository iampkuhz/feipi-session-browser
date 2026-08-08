package com.feipi.session.browser.index.api.write;

import java.time.Instant;
import java.util.Objects;

/**
 * 源 transcript 不可用时，已发现会话可写入索引的元数据。
 *
 * @param sessionKey 会话唯一键
 * @param agent 会话来源 agent
 * @param sessionId 来源系统中的会话 id
 * @param title 会话标题，可为空字符串
 * @param projectKey 项目唯一键
 * @param projectName 项目名称，可为空字符串
 * @param cwd 会话工作目录，可为空字符串
 * @param endedAt 会话结束时间文本
 * @param model 模型名称，可为空字符串
 * @param source 来源标识，可为空字符串
 * @param indexedAt 写入索引的时间
 */
public record MissingTranscriptSession(
    String sessionKey,
    String agent,
    String sessionId,
    String title,
    String projectKey,
    String projectName,
    String cwd,
    String endedAt,
    String model,
    String source,
    Instant indexedAt) {

  /**
   * 校验会话键、来源会话标识、agent、项目键、结束时间和索引时间，并将可选文本的 {@code null} 统一为空字符串。
   *
   * @throws NullPointerException 必填文本或 {@code indexedAt} 为 {@code null} 时抛出
   * @throws IllegalArgumentException 必填文本为空字符串时抛出
   */
  public MissingTranscriptSession {
    requireNonEmpty(sessionKey, "sessionKey");
    requireNonEmpty(agent, "agent");
    requireNonEmpty(sessionId, "sessionId");
    requireNonEmpty(projectKey, "projectKey");
    requireNonEmpty(endedAt, "endedAt");
    title = defaultEmpty(title);
    projectName = defaultEmpty(projectName);
    cwd = defaultEmpty(cwd);
    model = defaultEmpty(model);
    source = defaultEmpty(source);
    indexedAt = Objects.requireNonNull(indexedAt, "indexedAt 不得为 null");
  }

  private static void requireNonEmpty(String value, String name) {
    Objects.requireNonNull(value, name + " 不得为 null");
    if (value.isEmpty()) {
      throw new IllegalArgumentException(name + " 不得为空");
    }
  }

  private static String defaultEmpty(String value) {
    return value == null ? "" : value;
  }
}
