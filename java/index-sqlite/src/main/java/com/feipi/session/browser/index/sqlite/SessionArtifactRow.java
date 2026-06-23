package com.feipi.session.browser.index.sqlite;

import java.util.Objects;

/**
 * session_artifacts 表的类型化行数据。
 *
 * <p>承载 {@code session_artifacts} 表全部列的不可变值对象，记录每个会话关联的归一化制品路径和元数据。 主键为 {@code (sessionKey,
 * artifactType)} 组合。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionKey} 和 {@code artifactType} 不得为空字符串。
 *   <li>{@code path} 不得为 null，允许空字符串表示路径未定。
 *   <li>数值字段均非负。
 * </ul>
 *
 * @param sessionKey 所属会话主键
 * @param artifactType 制品类型标识（如 {@code "normalized"}、{@code "detail"}）
 * @param path 制品存储路径
 * @param schemaVersion 制品 schema 版本，缺失时为空字符串
 * @param sourcePath 源文件路径，缺失时为空字符串
 * @param sourceMtime 源文件修改时间（epoch 秒），非负
 * @param sizeBytes 制品文件大小（字节），非负
 * @param createdAt 创建时间戳（epoch 秒），非负
 * @param updatedAt 更新时间戳（epoch 秒），非负
 */
public record SessionArtifactRow(
    String sessionKey,
    String artifactType,
    String path,
    String schemaVersion,
    String sourcePath,
    double sourceMtime,
    long sizeBytes,
    double createdAt,
    double updatedAt) {

  /**
   * 紧凑构造器，验证 session_artifacts 表行不变量。
   *
   * @throws IllegalArgumentException 当主键字段为空字符串或数值字段为负数时
   */
  public SessionArtifactRow {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    if (sessionKey.isEmpty()) {
      throw new IllegalArgumentException("sessionKey 不得为空字符串");
    }
    Objects.requireNonNull(artifactType, "artifactType 不得为 null");
    if (artifactType.isEmpty()) {
      throw new IllegalArgumentException("artifactType 不得为空字符串");
    }
    path = path == null ? "" : path;
    schemaVersion = schemaVersion == null ? "" : schemaVersion;
    sourcePath = sourcePath == null ? "" : sourcePath;
    requireNonNegative(sourceMtime, "sourceMtime");
    requireNonNegative(sizeBytes, "sizeBytes");
    requireNonNegative(createdAt, "createdAt");
    requireNonNegative(updatedAt, "updatedAt");
  }

  private static void requireNonNegative(double value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
  }

  private static void requireNonNegative(long value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
  }
}
