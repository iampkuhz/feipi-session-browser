package com.feipi.session.browser.index.store.sqlite.loader;

import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedDiagnostic;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/** 转换单个有界内容对象，并保留来源追溯字段。 */
final class NormalizedContentCodec {
  private NormalizedContentCodec() {}

  /** 读取对象映射；可选对象缺失时返回空映射。 */
  @SuppressWarnings("unchecked")
  static Map<String, Object> map(Object value) {
    return value instanceof Map<?, ?> ? (Map<String, Object>) value : Map.of();
  }

  /** 读取规范字段名，并兼容历史字段别名。 */
  static Object field(Map<String, Object> m, String key, String alias) {
    return m.containsKey(key) ? m.get(key) : m.get(alias);
  }

  /** 读取可选数组，缺失时返回空列表。 */
  static List<?> list(Object value) {
    return value instanceof List<?> l ? l : List.of();
  }

  /** 读取字符串字段，缺失时返回空字符串。 */
  static String str(Map<String, Object> m, String k) {
    return Objects.toString(m.get(k), "");
  }

  /** 读取数值字段并转换为长整数。 */
  static long number(Object v) {
    return ((Number) v).longValue();
  }

  /** 读取可选字符串字段，保留缺失状态。 */
  static Optional<String> optional(Map<String, Object> m, String k) {
    return Optional.ofNullable(m.get(k)).map(Object::toString);
  }

  /** 还原结构化诊断信息，不丢弃诊断字段。 */
  static List<NormalizedDiagnostic> diagnostics(Map<String, Object> m) {
    return list(m.get("diagnostics")).stream().map(v -> new NormalizedDiagnostic(map(v))).toList();
  }

  /** 将有界来源目录映射还原为类型化条目。 */
  static Map<String, SourceUnitCatalogEntry> catalog(Map<String, Object> root) {
    Map<String, SourceUnitCatalogEntry> result = new LinkedHashMap<>();
    map(field(root, "sourceUnitCatalog", "source_unit_catalog"))
        .forEach(
            (key, value) -> {
              Map<String, Object> m = map(value), range = map(m.get("byteRange"));
              result.put(
                  key,
                  new SourceUnitCatalogEntry(
                      str(m, "unitKey"),
                      str(m, "originPath"),
                      str(m, "canonicalSourceLocator"),
                      str(m, "unitType"),
                      str(m, "candidate"),
                      SourceUnitDirection.fromValue(str(m, "direction")),
                      ((Number) m.getOrDefault("eventOrder", 0)).intValue(),
                      ((Number) m.getOrDefault("partIndex", 0)).intValue(),
                      new ByteRange(number(range.get("start")), number(range.get("end"))),
                      str(m, "contentHash"),
                      optional(m, "timestamp"),
                      optional(m, "label"),
                      ((Number) m.getOrDefault("priority", 50)).intValue(),
                      optional(m, "preview"),
                      optional(m, "text"),
                      m.get("payload"),
                      optional(m, "subSource"),
                      optional(m, "sourceCandidate"),
                      list(m.get("diagnostics")).stream()
                          .map(NormalizedContentCodec::map)
                          .toList()));
            });
    return result;
  }

  /** 还原旧格式的具名来源单元序列。 */
  static Map<String, List<String>> sequences(Map<String, Object> root) {
    Map<String, List<String>> result = new LinkedHashMap<>();
    map(field(root, "sourceUnitSequences", "source_unit_sequences"))
        .forEach((k, v) -> result.put(k, list(v).stream().map(Object::toString).toList()));
    return result;
  }

  /** 还原单个有界内容单元及其来源关联。 */
  static NormalizedContentUnit unit(Map<String, Object> m) {
    List<NormalizedSequenceChunk> chunks =
        list(m.get("sourceUnitSequences")).stream()
            .map(
                v -> {
                  Map<String, Object> chunk = map(v);
                  return new NormalizedSequenceChunk(
                      str(chunk, "name"),
                      number(chunk.get("offset")),
                      list(chunk.get("keys")).stream().map(Object::toString).toList());
                })
            .toList();
    return new NormalizedContentUnit(
        number(m.get("unitIndex")),
        NormalizedArtifactLoader.parseSourceFiles(m),
        NormalizedArtifactLoader.parseCalls(m),
        NormalizedArtifactLoader.parseToolExecutions(m),
        diagnostics(m),
        catalog(m),
        chunks);
  }

  /** 还原并保留调用的来源引用范围。 */
  static List<SourceUnitRefRange> ranges(Object value) {
    return list(value).stream()
        .map(
            v -> {
              Map<String, Object> m = map(v);
              return new SourceUnitRefRange(
                  optional(m, "sequence"),
                  ((Number) m.getOrDefault("start", 0)).intValue(),
                  ((Number) m.getOrDefault("end", 0)).intValue(),
                  list(m.get("refs")).stream().map(Object::toString).toList(),
                  optional(m, "role"));
            })
        .toList();
  }

  /** 还原完整逻辑会话的元数据和精确总量。 */
  static NormalizedContentHeader header(Map<String, Object> m) {
    Map<String, Long> totals = new LinkedHashMap<>();
    map(m.get("totals")).forEach((k, v) -> totals.put(k, number(v)));
    return new NormalizedContentHeader(
        str(m, "schemaVersion"),
        NormalizedAgent.fromValue(str(m, "agent")),
        new NormalizedSessionMetadata(map(m.get("session"))),
        totals);
  }
}
