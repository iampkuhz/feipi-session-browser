package com.feipi.session.browser.domain.normalized;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.TreeMap;

/** 基于已有列表的生产适配器；列表仍随输入规模增长，内容单元仅在游标读取时创建。 */
final class ListSessionContent implements NormalizedSessionContent {
  private final NormalizedContentHeader header;
  private final List<NormalizedSourceFile> sources;
  private final List<NormalizedCall> calls;
  private final List<NormalizedToolExecution> tools;
  private final List<NormalizedDiagnostic> diagnostics;
  private final Map<String, SourceUnitCatalogEntry> catalog;
  private final Map<String, List<String>> sequences;

  /** 保存生产结果的不可变列表与有序来源目录，并核对头部声明的总数。 */
  ListSessionContent(
      NormalizedContentHeader header,
      List<NormalizedSourceFile> sources,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      List<NormalizedDiagnostic> diagnostics,
      Map<String, SourceUnitCatalogEntry> catalog,
      Map<String, List<String>> sequences) {
    this.header = java.util.Objects.requireNonNull(header, "header");
    this.sources = List.copyOf(sources);
    this.calls = List.copyOf(calls);
    this.tools = List.copyOf(tools);
    this.diagnostics = List.copyOf(diagnostics);
    this.catalog = java.util.Collections.unmodifiableMap(new TreeMap<>(catalog));
    var sequenceCopy = new TreeMap<String, List<String>>();
    sequences.forEach((name, keys) -> sequenceCopy.put(name, List.copyOf(keys)));
    this.sequences = java.util.Collections.unmodifiableMap(sequenceCopy);
    if (!header.totals().equals(totals(sources, calls, tools, diagnostics, catalog, sequences))) {
      throw new IllegalArgumentException("content totals do not match producer lists");
    }
  }

  /** 汇总六项完整会话计数；序列项数是所有序列键数之和，不是片段数。 */
  static Map<String, Long> totals(
      List<NormalizedSourceFile> sources,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      List<NormalizedDiagnostic> diagnostics,
      Map<String, SourceUnitCatalogEntry> catalog,
      Map<String, List<String>> sequences) {
    return Map.of(
        "calls",
        (long) calls.size(),
        "toolExecutions",
        (long) tools.size(),
        "diagnostics",
        (long) diagnostics.size(),
        "sourceFiles",
        (long) sources.size(),
        "sourceUnitCatalog",
        (long) catalog.size(),
        "sourceUnitSequenceEntries",
        sequences.values().stream().mapToLong(List::size).sum());
  }

  /** 返回构造时校验过的完整会话元数据。 */
  @Override
  public NormalizedContentHeader header() {
    return header;
  }

  /** 为本次遍历创建独立游标，不缓存已生成的内容单元。 */
  @Override
  public ContentCursor openCursor() {
    return new Cursor();
  }

  /** 每种根集合每单元最多一条记录，使读取载荷接近一个既有领域对象的大小。 */
  private final class Cursor implements ContentCursor {
    private final Iterator<Map.Entry<String, SourceUnitCatalogEntry>> entries =
        catalog.entrySet().iterator();
    private final Iterator<Map.Entry<String, List<String>>> sequenceEntries =
        sequences.entrySet().iterator();
    private Map.Entry<String, List<String>> sequence;
    private int sequenceOffset;
    private int position;
    private boolean closed;

    /** 创建从首单元开始的独立内存游标；字段初始化器负责建立各集合的遍历位置。 */
    private Cursor() {}

    /** 检查各集合和来源序列是否仍有内容；关闭后明确拒绝继续读取。 */
    @Override
    public boolean hasNext() throws IOException {
      if (closed) {
        throw new IOException("content cursor is closed");
      }
      return position == 0
          || position < sources.size()
          || position < calls.size()
          || position < tools.size()
          || position < diagnostics.size()
          || entries.hasNext()
          || sequence != null
          || sequenceEntries.hasNext();
    }

    /** 按全局顺序生成下一个单元，并推进同名来源序列的连续偏移。 */
    @Override
    public NormalizedContentUnit next() throws IOException {
      if (!hasNext()) {
        throw new NoSuchElementException();
      }
      Map<String, SourceUnitCatalogEntry> entry = Map.of();
      if (entries.hasNext()) {
        var next = entries.next();
        entry = Map.of(next.getKey(), next.getValue());
      }
      if (sequence == null && sequenceEntries.hasNext()) {
        sequence = sequenceEntries.next();
        sequenceOffset = 0;
      }
      List<NormalizedSequenceChunk> chunks = List.of();
      if (sequence != null) {
        var keys = sequence.getValue();
        chunks =
            List.of(
                new NormalizedSequenceChunk(
                    sequence.getKey(),
                    sequenceOffset,
                    sequenceOffset < keys.size() ? List.of(keys.get(sequenceOffset)) : List.of()));
        sequenceOffset++;
        if (sequenceOffset >= keys.size()) {
          sequence = null;
        }
      }
      int index = position++;
      return new NormalizedContentUnit(
          index,
          one(sources, index),
          one(calls, index),
          one(tools, index),
          one(diagnostics, index),
          entry,
          chunks);
    }

    /** 标记游标已关闭；内存实现没有需要额外释放的外部资源。 */
    @Override
    public void close() {
      closed = true;
    }
  }

  /** 返回指定位置的单元素列表；超过该集合末尾时返回空列表。 */
  private static <T> List<T> one(List<T> values, int index) {
    return index < values.size() ? List.of(values.get(index)) : List.of();
  }

  /** 仅在原有容量内重建旧制品，同时复核单元连续性、来源唯一性、序列偏移及总数。 */
  static NormalizedSessionArtifact toArtifact(NormalizedSessionContent content) throws IOException {
    var header = content.header();
    if (header.totals().entrySet().stream()
        .anyMatch(
            entry ->
                entry.getValue()
                    > ("sourceUnitCatalog".equals(entry.getKey())
                        ? NormalizedConstants.MAX_SOURCE_UNIT_CATALOG_SIZE
                        : NormalizedConstants.MAX_COLLECTION_SIZE))) {
      throw new IllegalArgumentException("content exceeds legacy artifact collection limit");
    }
    var sources = new ArrayList<NormalizedSourceFile>();
    var calls = new ArrayList<NormalizedCall>();
    var tools = new ArrayList<NormalizedToolExecution>();
    var diagnostics = new ArrayList<NormalizedDiagnostic>();
    var catalog = new LinkedHashMap<String, SourceUnitCatalogEntry>();
    var sequences = new LinkedHashMap<String, List<String>>();
    long unitIndex = 0;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        if (unit.unitIndex() != unitIndex++) {
          throw new IOException("non-contiguous content unit");
        }
        append(sources, unit.sourceFiles());
        append(calls, unit.calls());
        append(tools, unit.toolExecutions());
        append(diagnostics, unit.diagnostics());
        for (var entry : unit.sourceUnitCatalog().entrySet()) {
          if (catalog.putIfAbsent(entry.getKey(), entry.getValue()) != null) {
            throw new IOException("duplicate source catalog key");
          }
        }
        for (var chunk : unit.sourceUnitSequences()) {
          var keys = sequences.computeIfAbsent(chunk.name(), key -> new ArrayList<>());
          if (keys.size() != chunk.offset()) {
            throw new IOException("non-contiguous sequence");
          }
          append(keys, chunk.keys());
        }
        if (catalog.size() > NormalizedConstants.MAX_SOURCE_UNIT_CATALOG_SIZE
            || sequences.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
          throw new IllegalArgumentException("content exceeds legacy artifact collection limit");
        }
      }
    }
    var actual = totals(sources, calls, tools, diagnostics, catalog, sequences);
    if (!header.totals().equals(actual)) {
      throw new IOException("content totals mismatch");
    }
    return new NormalizedSessionArtifact(
        header.schemaVersion(),
        header.agent(),
        sources,
        header.session(),
        calls,
        tools,
        diagnostics,
        catalog,
        sequences);
  }

  /** 在追加前检查合并后的集合容量，防止把新内容悄然合成超限旧制品。 */
  private static <T> void append(List<T> target, List<T> values) {
    if ((long) target.size() + values.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException("content exceeds legacy artifact collection limit");
    }
    target.addAll(values);
  }
}
