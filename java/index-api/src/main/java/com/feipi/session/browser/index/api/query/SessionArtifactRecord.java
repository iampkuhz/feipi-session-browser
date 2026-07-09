package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的抽象 session artifact 元数据。 */
public interface SessionArtifactRecord {
  String sessionKey();

  String artifactType();

  String path();

  String schemaVersion();

  String sourcePath();

  double sourceMtime();

  long sizeBytes();

  double createdAt();

  double updatedAt();
}
