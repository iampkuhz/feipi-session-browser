package com.feipi.session.browser.domain.normalized;

import java.io.IOException;
import java.util.Optional;

/** 可重复打开游标的完整逻辑会话内容，按有界单元遍历而不要求构造完整旧制品。 */
public interface NormalizedSessionContent {
  /** 返回不可变的完整会话元数据及跨单元总数。 */
  NormalizedContentHeader header();

  /** 从第零个内容单元打开独立游标；重开不会复用其他游标的遍历位置。 */
  ContentCursor openCursor() throws IOException;

  /**
   * 返回已经驻留的不可变旧制品视图；默认不推测、不读取游标，也不构造旧制品。
   *
   * @return 已有旧制品，流式内容及普通列表生产结果默认为空
   */
  default Optional<NormalizedSessionArtifact> legacyArtifact() {
    return Optional.empty();
  }

  /** 独立的内容遍历游标；关闭时释放底层读取资源。 */
  interface ContentCursor extends AutoCloseable {
    /** 判断是否还有下一个完整内容单元；读取失败时抛出异常而不视为空内容。 */
    boolean hasNext() throws IOException;

    /** 返回下一个内容单元；耗尽后抛出 NoSuchElementException。 */
    NormalizedContentUnit next() throws IOException;

    /** 关闭游标并释放底层读取资源。 */
    @Override
    void close() throws IOException;
  }

  /**
   * 将合法旧制品适配为可重放内容；保留会话身份、集合顺序及原有数据。
   *
   * @param artifact 已有的不可变旧制品
   * @return 同时保留原制品视图的可重放内容
   */
  static NormalizedSessionContent fromArtifact(NormalizedSessionArtifact artifact) {
    var content =
        fromLists(
            new NormalizedContentHeader(
                artifact.schemaVersion(),
                artifact.agent(),
                artifact.session(),
                ListSessionContent.totals(
                    artifact.sourceFiles(),
                    artifact.calls(),
                    artifact.toolExecutions(),
                    artifact.diagnostics(),
                    artifact.sourceUnitCatalog(),
                    artifact.sourceUnitSequences())),
            artifact.sourceFiles(),
            artifact.calls(),
            artifact.toolExecutions(),
            artifact.diagnostics(),
            artifact.sourceUnitCatalog(),
            artifact.sourceUnitSequences());
    return new NormalizedSessionContent() {
      /** 返回原制品对应的完整会话元数据。 */
      @Override
      public NormalizedContentHeader header() {
        return content.header();
      }

      /** 打开列表适配器的独立游标。 */
      @Override
      public ContentCursor openCursor() throws IOException {
        return content.openCursor();
      }

      /** 返回传入的原制品实例，不读取游标或重新组装正文。 */
      @Override
      public Optional<NormalizedSessionArtifact> legacyArtifact() {
        return Optional.of(artifact);
      }
    };
  }

  /** 按需把生产者列表切为有界单元；仍持有输入规模的列表，不代表归一化全链路使用常数内存。 */
  static NormalizedSessionContent fromLists(
      NormalizedContentHeader header,
      java.util.List<NormalizedSourceFile> sourceFiles,
      java.util.List<NormalizedCall> calls,
      java.util.List<NormalizedToolExecution> toolExecutions,
      java.util.List<NormalizedDiagnostic> diagnostics,
      java.util.Map<String, SourceUnitCatalogEntry> sourceUnitCatalog,
      java.util.Map<String, java.util.List<String>> sourceUnitSequences) {
    return new ListSessionContent(
        header,
        sourceFiles,
        calls,
        toolExecutions,
        diagnostics,
        sourceUnitCatalog,
        sourceUnitSequences);
  }

  /** 仅将各项总数满足原有容量限制的内容转为旧制品，并在遍历中复核实际数量。 */
  default NormalizedSessionArtifact toArtifact() throws IOException {
    return ListSessionContent.toArtifact(this);
  }

  /**
   * 用新元数据包装同一内容；不读取游标，已有旧制品仅共享正文对象建立新元数据浅视图。
   *
   * @param replacement 替换后的完整会话元数据
   * @return 不额外获得内容所有权的包装视图
   */
  default NormalizedSessionContent withHeader(NormalizedContentHeader replacement) {
    java.util.Objects.requireNonNull(replacement, "replacement");
    var delegate = this;
    var legacy =
        legacyArtifact()
            .map(
                artifact ->
                    new NormalizedSessionArtifact(
                        replacement.schemaVersion(),
                        replacement.agent(),
                        artifact.sourceFiles(),
                        replacement.session(),
                        artifact.calls(),
                        artifact.toolExecutions(),
                        artifact.diagnostics(),
                        artifact.sourceUnitCatalog(),
                        artifact.sourceUnitSequences()));
    return new NormalizedSessionContent() {
      /** 返回包装时指定的完整会话元数据。 */
      @Override
      public NormalizedContentHeader header() {
        return replacement;
      }

      /** 委托原内容打开独立游标，保持读取行为及资源生命周期不变。 */
      @Override
      public ContentCursor openCursor() throws IOException {
        return delegate.openCursor();
      }

      /** 返回与替换元数据一致的已有旧制品浅视图；没有原视图时仍为空。 */
      @Override
      public Optional<NormalizedSessionArtifact> legacyArtifact() {
        return legacy;
      }
    };
  }
}
