package com.feipi.session.browser.domain.normalized;

import java.util.List;
import java.util.Map;

/**
 * 有界的会话内容单元；调用、来源及关联标识始终属于整个逻辑会话，不随单元重新编号。
 *
 * @param unitIndex 从零开始且跨单元连续递增的存储顺序编号
 * @param sourceFiles 本单元首次提供的来源文件，不为分页重复复制
 * @param calls 按完整会话顺序排列的调用，保留全局标识及调用编号
 * @param toolExecutions 保留全局调用关联的工具执行记录
 * @param diagnostics 本单元包含的解析诊断，不表示完整会话的诊断总数
 * @param sourceUnitCatalog 本单元提供的来源目录条目，目录键在整个会话内唯一
 * @param sourceUnitSequences 携带全局偏移的来源序列片段，可跨单元连续读取
 */
public record NormalizedContentUnit(
    long unitIndex,
    List<NormalizedSourceFile> sourceFiles,
    List<NormalizedCall> calls,
    List<NormalizedToolExecution> toolExecutions,
    List<NormalizedDiagnostic> diagnostics,
    Map<String, SourceUnitCatalogEntry> sourceUnitCatalog,
    List<NormalizedSequenceChunk> sourceUnitSequences) {
  /** 验证单元编号非负，并分别复制各集合、检查原有集合容量限制。 */
  public NormalizedContentUnit {
    if (unitIndex < 0) {
      throw new IllegalArgumentException("unitIndex must be nonnegative");
    }
    sourceFiles = bounded(sourceFiles, "sourceFiles");
    calls = bounded(calls, "calls");
    toolExecutions = bounded(toolExecutions, "toolExecutions");
    diagnostics = bounded(diagnostics, "diagnostics");
    sourceUnitCatalog = Map.copyOf(sourceUnitCatalog);
    if (sourceUnitCatalog.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException("sourceUnitCatalog size exceeds limit");
    }
    sourceUnitSequences = bounded(sourceUnitSequences, "sourceUnitSequences");
  }

  /** 创建列表的不可变副本；超过原有集合容量时拒绝，避免截断内容。 */
  private static <T> List<T> bounded(List<T> values, String name) {
    var copy = List.copyOf(values);
    if (copy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(name + " size exceeds limit");
    }
    return copy;
  }
}
