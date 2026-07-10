package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.SessionArtifactRecord;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

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
    /* 所属会话主键。 */ @NotBlank String sessionKey,
    /* 制品类型标识（如 "normalized"、"detail"）。 */ @NotBlank String artifactType,
    /* 制品存储路径。 */ String path,
    /* 制品 schema 版本，缺失时为空字符串。 */ String schemaVersion,
    /* 源文件路径，缺失时为空字符串。 */ String sourcePath,
    /* 源文件修改时间（epoch 秒），非负。 */ @PositiveOrZero double sourceMtime,
    /* 制品文件大小（字节），非负。 */ @PositiveOrZero long sizeBytes,
    /* 创建时间戳（epoch 秒），非负。 */ @PositiveOrZero double createdAt,
    /* 更新时间戳（epoch 秒），非负。 */ @PositiveOrZero double updatedAt)
    implements SessionArtifactRecord {

  /**
   * 紧凑构造器，校验 record component 约束并应用默认值。
   *
   * @throws IllegalArgumentException 当主键字段为空字符串或数值字段为负数时
   */
  public SessionArtifactRow {
    ValidationSupport.validateCanonicalConstructor(
        SessionArtifactRow.class,
        sessionKey,
        artifactType,
        path,
        schemaVersion,
        sourcePath,
        sourceMtime,
        sizeBytes,
        createdAt,
        updatedAt);
    path = path == null ? "" : path;
    schemaVersion = schemaVersion == null ? "" : schemaVersion;
    sourcePath = sourcePath == null ? "" : sourcePath;
  }
}
