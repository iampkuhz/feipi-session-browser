package com.feipi.session.browser.index.api.imports;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.query.SessionRecord;
import java.util.Objects;

/**
 * 与个人索引无关的单文件分析结果。
 *
 * @param metadata 导入身份与显示信息
 * @param sessionRow 供既有详情装配器消费的只读行投影
 * @param artifact 复用既有归一化流水线生成的完整制品
 */
public record ImportedSessionAnalysis(
    ImportedSessionMetadata metadata,
    SessionRecord sessionRow,
    NormalizedSessionArtifact artifact) {

  /** 确保单文件结果不可缺少任何投影。 */
  public ImportedSessionAnalysis {
    Objects.requireNonNull(metadata, "metadata");
    Objects.requireNonNull(sessionRow, "sessionRow");
    Objects.requireNonNull(artifact, "artifact");
  }
}
