package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;

/** 工具级结果使用独立来源目录；调用中的同次结果仅作为缺目录时的来源。 */
final class ToolResultContents<T> {
  private final Map<String, Occurrences<T>> results = new LinkedHashMap<>();
  private final Projection<T> projection;

  ToolResultContents(Projection<T> projection) {
    this.projection = projection;
  }

  T inline(Map<String, Object> source) throws IOException {
    String id = PayloadCallContentExtractor.toolResultId(source);
    if (!PayloadCallContentExtractor.isToolResult(source.get("type")) || id.isEmpty()) return null;
    String text =
        PayloadCallContentExtractor.resolveInline(List.of(source), null, "tool_result", id);
    if (text.isEmpty()) return null;
    T value = projection.apply(text);
    bucket(id).inline.add(value);
    return value;
  }

  void catalog(SourceUnitCatalogEntry entry) throws IOException {
    Map<?, ?> payload = entry.payload() instanceof Map<?, ?> map ? map : Map.of();
    if (!PayloadCallContentExtractor.isToolResult(entry.unitType())
        && !PayloadCallContentExtractor.isToolResult(payload.get("type"))) return;
    String id = PayloadCallContentExtractor.toolResultId(payload);
    boolean independent = entry.unitKey().startsWith("tool-result:");
    long ordinal = 0;
    if (independent) {
      int separator = entry.unitKey().indexOf(':', "tool-result:".length());
      if (separator < 0
          || !entry.unitKey().substring(separator + 1).equals(entry.canonicalSourceLocator())
          || !"tool_result".equals(entry.unitType())
          || !"tool_result".equals(payload.get("type"))
          || !"request".equals(entry.direction().getValue())
          || id.isEmpty()
          || entry.label().filter(id::equals).isEmpty()) return;
      try {
        ordinal = Long.parseLong(entry.unitKey().substring("tool-result:".length(), separator));
      } catch (NumberFormatException invalid) {
        return;
      }
      if (ordinal < 0) return;
    }
    var ids = new HashSet<String>();
    entry.label().ifPresent(ids::add);
    if (!id.isEmpty()) ids.add(id);
    var order =
        new Order(
            ordinal,
            entry.eventOrder(),
            entry.partIndex(),
            entry.canonicalSourceLocator(),
            entry.unitKey());
    for (String tool : ids) {
      var target = independent ? bucket(tool).independent : bucket(tool).catalog;
      if (!target.containsKey(order))
        target.put(order, projection.apply(PayloadCallContentExtractor.catalogEntryText(entry)));
    }
  }

  List<T> occurrences(String id) {
    var found = results.get(id);
    if (found == null) return List.of();
    if (!found.independent.isEmpty()) return List.copyOf(found.independent.values());
    if (!found.inline.isEmpty()) return List.copyOf(found.inline);
    return List.copyOf(found.catalog.values());
  }

  Iterable<String> ids() {
    return results.keySet();
  }

  private Occurrences<T> bucket(String id) {
    return results.computeIfAbsent(id, ignored -> new Occurrences<>());
  }

  static Optional<String> join(List<String> texts) {
    return texts.isEmpty() ? Optional.empty() : Optional.of(String.join("\n\n", texts));
  }

  /** 将正文投影到现有私有文件偏移或单个目标的正文。 */
  @FunctionalInterface
  interface Projection<T> {
    T apply(String text) throws IOException;
  }

  /** 同一工具只保留正文投影及稳定来源排序键。 */
  private static final class Occurrences<T> {
    private final List<T> inline = new ArrayList<>();
    private final TreeMap<Order, T> catalog = new TreeMap<>();
    private final TreeMap<Order, T> independent = new TreeMap<>();
  }

  /**
   * 来源排序键不持有正文；独立目录以原始 ordinal 排序，其他目录沿事件和分块排序。
   *
   * @param ordinal 独立来源记录序号
   * @param event 来源事件序号
   * @param part 事件内分块序号
   * @param locator 稳定来源位置
   * @param key 稳定目录身份
   */
  private record Order(long ordinal, int event, int part, String locator, String key)
      implements Comparable<Order> {
    @Override
    public int compareTo(Order other) {
      int result = Long.compare(ordinal, other.ordinal);
      if (result == 0) result = Integer.compare(event, other.event);
      if (result == 0) result = Integer.compare(part, other.part);
      if (result == 0) result = locator.compareTo(other.locator);
      return result == 0 ? key.compareTo(other.key) : result;
    }
  }
}
