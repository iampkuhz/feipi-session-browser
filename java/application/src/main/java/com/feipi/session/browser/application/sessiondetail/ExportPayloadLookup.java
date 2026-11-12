package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** 导出生命周期的私有磁盘正文索引；内存仅保存身份、偏移和序列键。 */
final class ExportPayloadLookup implements AutoCloseable {
  private final Path path;
  private final RandomAccessFile file;
  private final Map<String, CatalogText> catalog = new HashMap<>();
  private final Map<String, java.util.TreeMap<Long, List<SequenceKey>>> sequences = new HashMap<>();
  private final Map<String, InputOffsets> inputs = new HashMap<>();
  private final Map<String, Offset> inlineResults = new HashMap<>();
  private final Map<String, Offset> catalogResults = new HashMap<>();
  private final Set<String> tools = new HashSet<>();
  private long sequenceOrder;

  private ExportPayloadLookup(Path path, RandomAccessFile file) {
    this.path = path;
    this.file = file;
  }

  static ExportPayloadLookup build(NormalizedSessionContent content) throws IOException {
    return build(content, null);
  }

  /** 测试可指定私有临时目录，不增加运行时配置或持久缓存。 */
  static ExportPayloadLookup build(NormalizedSessionContent content, Path directory)
      throws IOException {
    var permissions =
        PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------"));
    Path path =
        directory == null
            ? Files.createTempFile("feipi-export-lookup-", ".tmp", permissions)
            : Files.createTempFile(directory, "feipi-export-lookup-", ".tmp", permissions);
    boolean complete = false;
    ExportPayloadLookup lookup = null;
    try {
      lookup = new ExportPayloadLookup(path, new RandomAccessFile(path.toFile(), "rw"));
      lookup.collect(content);
      complete = true;
      return lookup;
    } finally {
      if (!complete) {
        if (lookup != null) lookup.close();
        else Files.deleteIfExists(path);
      }
    }
  }

  private void collect(NormalizedSessionContent content) throws IOException {
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        for (var call : unit.calls()) {
          tools.addAll(call.response().toolCallIds());
          for (var source : call.sourceUnits()) {
            if (!"user".equals(source.get("role"))) collectInputs(source);
            String id = PayloadCallContentExtractor.toolResultId(source);
            if (PayloadCallContentExtractor.isToolResult(source.get("type"))
                && !id.isEmpty()
                && !inlineResults.containsKey(id)) {
              String text =
                  PayloadCallContentExtractor.resolveInline(
                      call.sourceUnits(), null, "tool_result", id);
              if (!text.isEmpty()) inlineResults.put(id, write(text));
            }
          }
        }
        for (var tool : unit.toolExecutions()) tools.add(tool.toolCallId());
        for (var chunk : unit.sourceUnitSequences()) {
          var positions = sequences.computeIfAbsent(chunk.name(), key -> new java.util.TreeMap<>());
          for (int i = 0; i < chunk.keys().size(); i++) {
            positions
                .computeIfAbsent(chunk.offset() + i, key -> new ArrayList<>())
                .add(new SequenceKey(sequenceOrder++, chunk.keys().get(i)));
          }
        }
        for (var item : unit.sourceUnitCatalog().entrySet()) {
          var entry = item.getValue();
          if (!catalog.containsKey(item.getKey())) {
            boolean request = "request".equals(entry.direction().getValue());
            boolean visible =
                !List.of("tool_use", "function_call", "custom_tool_call")
                    .contains(entry.unitType());
            catalog.put(
                item.getKey(),
                new CatalogText(
                    request,
                    visible,
                    PayloadCallContentExtractor.isReadingEntry(
                        entry, java.util.Optional.empty(), request),
                    PayloadCallContentExtractor.isReadingEntry(
                        entry, java.util.Optional.of(request ? "user" : "assistant"), request),
                    write(PayloadCallContentExtractor.catalogEntryText(entry))));
          }
          Map<?, ?> payload = entry.payload() instanceof Map<?, ?> map ? map : Map.of();
          if ("response".equals(entry.direction().getValue())) collectInputs(payload);
          if (PayloadCallContentExtractor.isToolResult(entry.unitType())
              || PayloadCallContentExtractor.isToolResult(payload.get("type"))) {
            // 与单项读取器一致，标签和载荷工具身份可以指向同一条目。
            if (entry.label().isPresent()) collectResult(entry.label().get(), entry);
            String id = PayloadCallContentExtractor.toolResultId(payload);
            if (!id.isEmpty()) collectResult(id, entry);
          }
        }
      }
    }
  }

  private void collectResult(
      String id, com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry entry)
      throws IOException {
    if (!catalogResults.containsKey(id)) {
      catalogResults.put(id, write(PayloadCallContentExtractor.catalogEntryText(entry)));
    }
  }

  private void collectInputs(Map<?, ?> source) throws IOException {
    var found = new LinkedHashMap<String, ToolInputContents.Input>();
    ToolInputContents.collect(source, found);
    for (var input : found.values()) {
      if (!inputs.containsKey(input.id())) {
        inputs.put(input.id(), new InputOffsets(write(input.name()), write(input.input())));
      }
    }
  }

  String catalogText(String key, boolean request) throws IOException {
    var value = catalog.get(key);
    return value != null && value.request() == request && value.visible() ? read(value.text()) : "";
  }

  boolean isReadingText(String key, boolean hasRole) {
    var value = catalog.get(key);
    return value != null && (hasRole ? value.readingWithRole() : value.reading());
  }

  void forEachRef(SourceUnitRefRange range, RefConsumer action) throws IOException {
    if (!range.refs().isEmpty() || range.sequence().isEmpty()) {
      for (String key : range.refs()) action.accept(key);
      return;
    }
    var positions = sequences.get(range.sequence().get());
    if (positions == null) return;
    var selected = new ArrayList<SequenceKey>();
    positions
        .subMap((long) range.start(), true, (long) range.end(), false)
        .values()
        .forEach(selected::addAll);
    selected.sort(java.util.Comparator.comparingLong(SequenceKey::order));
    for (var key : selected) action.accept(key.key());
  }

  Optional<ToolInputContents.Input> input(String id) throws IOException {
    var value = inputs.get(id);
    return value == null
        ? Optional.empty()
        : Optional.of(new ToolInputContents.Input(id, read(value.name()), read(value.input())));
  }

  Optional<String> result(String id) throws IOException {
    var value = inlineResults.getOrDefault(id, catalogResults.get(id));
    return value == null ? Optional.empty() : Optional.of(read(value));
  }

  boolean hasTool(String id) {
    return tools.contains(id);
  }

  private Offset write(String text) throws IOException {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    long offset = file.length();
    file.seek(offset);
    file.write(bytes);
    return new Offset(offset, bytes.length);
  }

  private String read(Offset offset) throws IOException {
    byte[] bytes = new byte[offset.length()];
    file.seek(offset.position());
    file.readFully(bytes);
    return new String(bytes, StandardCharsets.UTF_8);
  }

  @Override
  public void close() throws IOException {
    try {
      file.close();
    } finally {
      Files.deleteIfExists(path);
    }
  }

  /**
   * 单项正文在私有文件中的字节范围。
   *
   * @param position 正文首字节的文件偏移
   * @param length 正文编码后的字节数
   */
  private record Offset(long position, int length) {}

  /**
   * 目录首次出现的方向和正文偏移。
   *
   * @param request 是否属于请求方向
   * @param visible 是否包含在原始调用记录中
   * @param reading 没有区间角色时是否属于对话正文
   * @param readingWithRole 有匹配区间角色时是否属于对话正文
   * @param text 正文的磁盘位置
   */
  private record CatalogText(
      boolean request, boolean visible, boolean reading, boolean readingWithRole, Offset text) {}

  /**
   * 工具参数的名称及正文偏移，不在内存保留正文。
   *
   * @param name 工具名称的磁盘位置
   * @param input 参数正文的磁盘位置
   */
  private record InputOffsets(Offset name, Offset input) {}

  /**
   * 序列仅保存紧凑身份键，保持原始片段及重复出现顺序。
   *
   * @param order 引用在原始片段重放中的出现顺序
   * @param key 引用的目录身份键
   */
  private record SequenceKey(long order, String key) {}

  /** 逐个消费引用，不物化整项引用正文。 */
  @FunctionalInterface
  interface RefConsumer {
    void accept(String key) throws IOException;
  }
}
