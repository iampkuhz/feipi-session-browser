package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 从权威 usage 的字段存在性保留四段用量精度，明确区分真实零和缺失值。 */
final class CodexTokenProvenance {
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

  static boolean hasCompleteUsage(JsonNode usage) {
    return FIELDS.values().stream()
        .allMatch(aliases -> aliases.stream().anyMatch(alias -> usage.path(alias).isNumber()));
  }

  void addUsage(JsonNode usage) {
    FIELDS.forEach(
        (key, aliases) ->
            precisions
                .get(key)
                .add(
                    aliases.stream().anyMatch(alias -> usage.path(alias).isNumber())
                        ? "provider_reported"
                        : "unavailable"));
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
