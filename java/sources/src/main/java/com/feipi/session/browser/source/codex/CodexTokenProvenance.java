package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 从权威 usage 的合法数值和计算依赖保留四段用量精度，明确区分真实零和不可用值。 */
final class CodexTokenProvenance {
  private static final String PROVIDER_REPORTED = "provider_reported";
  private static final Map<String, List<String>> FIELDS =
      Map.of(
          "freshInputTokenPrecision", List.of("input_tokens", "inputTokens", "prompt_tokens"),
          "cacheReadTokenPrecision",
              List.of(
                  "cached_input_tokens",
                  "cache_read_input_tokens",
                  "cacheReadInputTokens",
                  "cached_tokens"),
          "cacheWriteTokenPrecision",
              List.of(
                  "cache_write_input_tokens",
                  "cache_creation_input_tokens",
                  "cacheCreationInputTokens"),
          "outputTokenPrecision", List.of("output_tokens", "outputTokens", "completion_tokens"));

  private final Map<String, Set<String>> precisions = new LinkedHashMap<>();

  CodexTokenProvenance() {
    FIELDS.keySet().forEach(key -> precisions.put(key, new LinkedHashSet<>()));
  }

  static boolean hasCompleteUsage(JsonNode usage, boolean responseUsage) {
    return FIELDS.values().stream().allMatch(aliases -> readUsageLong(usage, aliases) != null)
        && freshInput(usage, responseUsage) != null;
  }

  static Map<String, String> forUsage(JsonNode usage, boolean responseUsage) {
    Map<String, String> result = new LinkedHashMap<>();
    FIELDS.forEach(
        (key, aliases) ->
            result.put(
                key, readUsageLong(usage, aliases) != null ? PROVIDER_REPORTED : "unavailable"));
    if (freshInput(usage, responseUsage) == null) {
      result.put("freshInputTokenPrecision", "unavailable");
    }
    var provenance = new CodexTokenProvenance();
    provenance.addProvenance(result);
    return provenance.metadata();
  }

  /** 与用量读取保持相同别名优先级；首个数字字段非法时，不借后续别名背书。 */
  static Long readUsageLong(JsonNode usage, List<String> aliases) {
    if (usage == null || !usage.isObject()) {
      return null;
    }
    for (String alias : aliases) {
      JsonNode value = usage.get(alias);
      if (value != null && value.isNumber()) {
        return value.isIntegralNumber() && value.canConvertToLong() && value.longValue() >= 0
            ? value.longValue()
            : null;
      }
    }
    return null;
  }

  static long component(JsonNode usage, String precision) {
    Long value = readUsageLong(usage, FIELDS.get(precision));
    return value == null ? 0 : value;
  }

  /** 先逐段验证包含关系，再相减，避免 cache 合计或减法溢出。 */
  static Long freshInput(JsonNode usage, boolean responseUsage) {
    return freshInput(usage, responseUsage, false);
  }

  static long freshInputAmount(JsonNode usage, boolean responseUsage) {
    Long value = freshInput(usage, responseUsage, true);
    return value == null ? 0 : value;
  }

  private static Long freshInput(JsonNode usage, boolean responseUsage, boolean allowMissingCache) {
    Long input = readUsageLong(usage, FIELDS.get("freshInputTokenPrecision"));
    if (input == null) {
      return null;
    }
    boolean inclusive =
        responseUsage
            || (usage.has("cached_input_tokens") && !usage.has("cache_read_input_tokens"));
    if (!inclusive) {
      return input;
    }
    Long read = cacheDependency(usage, "cacheReadTokenPrecision", allowMissingCache);
    Long write =
        responseUsage
            ? cacheDependency(usage, "cacheWriteTokenPrecision", allowMissingCache)
            : Long.valueOf(0);
    if (read == null || write == null || read > input || write > input - read) {
      return null;
    }
    return input - read - write;
  }

  private static Long cacheDependency(JsonNode usage, String precision, boolean allowMissing) {
    List<String> aliases = FIELDS.get(precision);
    Long value = readUsageLong(usage, aliases);
    // 缺字段沿用既有数量算术，但 provenance 仍不可用；非法数字绝不按缺字段处理。
    return value == null
            && allowMissing
            && aliases.stream().noneMatch(alias -> usage.path(alias).isNumber())
        ? Long.valueOf(0)
        : value;
  }

  static Map<String, String> deltaProvenance(
      Map<String, String> current, Map<String, String> previous) {
    Map<String, String> result = new LinkedHashMap<>();
    FIELDS
        .keySet()
        .forEach(
            key ->
                result.put(
                    key,
                    PROVIDER_REPORTED.equals(current.get(key))
                            && PROVIDER_REPORTED.equals(previous.get(key))
                        ? PROVIDER_REPORTED
                        : PROVIDER_REPORTED.equals(current.get(key))
                            ? "unknown"
                            : current.getOrDefault(key, "unknown")));
    var provenance = new CodexTokenProvenance();
    provenance.addProvenance(result);
    return provenance.metadata();
  }

  static Map<String, String> reportedZero() {
    Map<String, String> result = new LinkedHashMap<>();
    FIELDS.keySet().forEach(key -> result.put(key, PROVIDER_REPORTED));
    return Map.copyOf(result);
  }

  void addProvenance(Map<String, String> source) {
    precisions.forEach((key, values) -> values.add(source.getOrDefault(key, "unknown")));
  }

  void addUnknown() {
    precisions.values().forEach(values -> values.add("unknown"));
  }

  Map<String, String> metadata() {
    Map<String, String> result = new LinkedHashMap<>();
    precisions.forEach(
        (key, values) ->
            result.put(
                key,
                values.size() > 1
                    ? "mixed"
                    : values.isEmpty() ? "unknown" : values.iterator().next()));
    result.put("tokenEstimationMethod", "");
    result.put("tokenContainsEstimated", "false");
    result.put("tokenContainsUnavailable", Boolean.toString(contains("unavailable")));
    result.put("tokenContainsUnknown", Boolean.toString(contains("unknown")));
    return Map.copyOf(result);
  }

  private boolean contains(String precision) {
    return precisions.values().stream()
        .anyMatch(
            values -> values.isEmpty() ? "unknown".equals(precision) : values.contains(precision));
  }
}
