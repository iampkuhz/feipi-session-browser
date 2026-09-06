package com.feipi.session.browser.index.api.write;

import java.util.Objects;

/**
 * 增量扫描状态分类使用的最小已存会话 fingerprint。
 *
 * @param sessionKey 会话唯一键
 * @param filePath 来源文件路径，可为空字符串
 * @param fileMtime 来源文件修改时间
 * @param agent 会话来源 agent
 * @param endedAt 会话结束时间文本，可为空字符串
 * @param title 会话标题，可为空字符串
 * @param projectKey 项目唯一键，可为空字符串
 * @param cwd 工作目录，可为空字符串
 */
public record StoredSessionFingerprint(
    String sessionKey,
    String filePath,
    double fileMtime,
    String agent,
    String endedAt,
    String title,
    String projectKey,
    String cwd) {

  /**
   * 完整构造器，包含元数据字段。
   *
   * @throws NullPointerException {@code sessionKey} 或 {@code agent} 为 {@code null} 时抛出
   * @throws IllegalArgumentException {@code sessionKey} 为空或 {@code fileMtime} 为负数时抛出
   */
  public StoredSessionFingerprint {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    if (sessionKey.isEmpty()) {
      throw new IllegalArgumentException("sessionKey 不得为空");
    }
    filePath = filePath == null ? "" : filePath;
    Objects.requireNonNull(agent, "agent 不得为 null");
    if (fileMtime < 0) {
      throw new IllegalArgumentException("fileMtime 不得为负: " + fileMtime);
    }
    endedAt = endedAt == null ? "" : endedAt;
    title = title == null ? "" : title;
    projectKey = projectKey == null ? "" : projectKey;
    cwd = cwd == null ? "" : cwd;
  }

  /**
   * 向后兼容构造器，不含元数据字段。
   *
   * @deprecated 使用包含元数据字段的完整构造器
   */
  @Deprecated
  public StoredSessionFingerprint(
      String sessionKey, String filePath, double fileMtime, String agent, String endedAt) {
    this(sessionKey, filePath, fileMtime, agent, endedAt, "", "", "");
  }
}
