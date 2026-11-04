package com.feipi.session.browser.index.api.imports;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import java.time.Instant;
import java.util.Objects;

/**
 * 导入分析的独立身份与安全显示元数据，不包含服务器路径。
 *
 * @param importId 随机导入标识，不使用来源会话 ID
 * @param source 用户明确选择的来源
 * @param filename 仅用于显示的文件名，不含目录
 * @param originalSessionId 文件内的来源会话 ID，缺失时为空
 * @param sizeBytes 本文件字节数
 * @param createdAt 导入创建时间
 */
public record ImportedSessionMetadata(
    String importId,
    NormalizedAgent source,
    String filename,
    String originalSessionId,
    long sizeBytes,
    Instant createdAt) {

  /** 拒绝不完整的导入身份。 */
  public ImportedSessionMetadata {
    Objects.requireNonNull(importId, "importId");
    Objects.requireNonNull(source, "source");
    Objects.requireNonNull(filename, "filename");
    Objects.requireNonNull(originalSessionId, "originalSessionId");
    Objects.requireNonNull(createdAt, "createdAt");
    if (importId.isBlank() || filename.isBlank() || sizeBytes < 0) {
      throw new IllegalArgumentException("导入元数据无效");
    }
  }
}
