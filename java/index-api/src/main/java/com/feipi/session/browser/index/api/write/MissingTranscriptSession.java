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
 * @param startedAt 会话开始时间文本，未知为空
 * @param endedAt 会话结束时间文本，未知为空
 * @param gitBranch 源 Git 分支，未知为空
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
    String startedAt,
    String endedAt,
    String gitBranch,
    String model,
    String source,
    Instant indexedAt) {

  /**
   * 校验会话键、来源会话标识、agent 和索引时间，并将可选文本的 {@code null} 统一为空字符串。
   *
   * @throws NullPointerException 必填文本或 {@code indexedAt} 为 {@code null} 时抛出
   * @throws IllegalArgumentException 必填文本为空字符串时抛出
   */
  public MissingTranscriptSession {
    requireNonEmpty(sessionKey, "sessionKey");
    requireNonEmpty(agent, "agent");
    requireNonEmpty(sessionId, "sessionId");
    projectKey = defaultEmpty(projectKey);
    startedAt = defaultEmpty(startedAt);
    endedAt = defaultEmpty(endedAt);
    gitBranch = defaultEmpty(gitBranch);
    title = defaultEmpty(title);
    projectName = defaultEmpty(projectName);
    cwd = defaultEmpty(cwd);
    model = defaultEmpty(model);
    source = defaultEmpty(source);
    indexedAt = Objects.requireNonNull(indexedAt, "indexedAt 不得为 null");
  }

  /** 兼容仅提供结束时间的调用方；未提供的开始时间保持未知。 */
  public MissingTranscriptSession(
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
    this(
        sessionKey,
        agent,
        sessionId,
        title,
        projectKey,
        projectName,
        cwd,
        "",
        endedAt,
        "",
        model,
        source,
        indexedAt);
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
