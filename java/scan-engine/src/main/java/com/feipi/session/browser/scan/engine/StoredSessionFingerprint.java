package com.feipi.session.browser.scan.engine;

import java.util.Objects;

/**
 * 从 sessions 表加载的已索引会话指纹数据。
 *
 * <p>用于增量扫描时与当前候选项指纹对比，判断会话是否发生变化。 该 record 仅承载增量比较所需的最小字段集，不映射 sessions 表全部列。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionKey} 不得为 null 或空。
 *   <li>{@code agent} 不得为 null。
 *   <li>{@code fileMtime} 非负（epoch 秒）。
 * </ul>
 *
 * @param sessionKey 会话主键
 * @param filePath 已索引的源文件路径，空字符串表示路径未知
 * @param fileMtime 已索引的源文件修改时间（epoch 秒），0 表示未知
 * @param agent 源适配器协议值
 * @param endedAt 会话结束时间（ISO 格式字符串），用于 age cutoff 过滤
 */
public record StoredSessionFingerprint(
    String sessionKey, String filePath, double fileMtime, String agent, String endedAt) {

  /**
   * 紧凑构造器，验证不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   * @throws IllegalArgumentException 当 sessionKey 为空时
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
  }
}
