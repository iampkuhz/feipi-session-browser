package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的抽象 session artifact 元数据。 */
public interface SessionArtifactRecord {
  /** 返回 artifact 所属会话的唯一键。 */
  String sessionKey();

  /** 返回制品类型标识。 */
  String artifactType();

  /** 返回制品的存储路径。 */
  String path();

  /** 返回制品内容遵循的 schema 版本。 */
  String schemaVersion();

  /** 返回生成 artifact 的源文件路径。 */
  String sourcePath();

  /** 返回源文件修改时间的 epoch 秒数。 */
  double sourceMtime();

  /** 返回制品的字节大小。 */
  long sizeBytes();

  /** 返回制品创建时间的 epoch 秒数。 */
  double createdAt();

  /** 返回制品最近更新时间的 epoch 秒数。 */
  double updatedAt();
}
