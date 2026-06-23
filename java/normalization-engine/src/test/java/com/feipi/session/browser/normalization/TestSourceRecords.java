package com.feipi.session.browser.normalization;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/** 测试用源中性记录工厂。 */
final class TestSourceRecords {

  /** 防止实例化。 */
  private TestSourceRecords() {}

  static SourceRecord ofType(String eventType) {
    return SourceRecord.of("test#event[0]", 0, eventType);
  }

  static SourceRecord from(JsonNode node, int index) {
    String type = text(node, "type").orElse("unknown");
    return new SourceRecord(
        "test#event[" + index + "]",
        index,
        type,
        firstText(node, "id", "uuid"),
        text(node, "model"),
        text(node, "timestamp"),
        firstText(node, "turn_id", "turnId"),
        usage(node),
        toolCalls(node),
        text(node, "tool_use_id"),
        text(node, "name"));
  }

  static List<SourceRecord> records(JsonNode... nodes) {
    List<SourceRecord> records = new ArrayList<>();
    for (int i = 0; i < nodes.length; i++) {
      records.add(from(nodes[i], i));
    }
    return List.copyOf(records);
  }

  static List<SourceRecord> records(List<? extends JsonNode> nodes) {
    List<SourceRecord> records = new ArrayList<>();
    for (int i = 0; i < nodes.size(); i++) {
      JsonNode node = nodes.get(i);
      if (node != null) {
        records.add(from(node, i));
      }
    }
    return List.copyOf(records);
  }

  private static Optional<String> firstText(JsonNode node, String... fields) {
    for (String field : fields) {
      Optional<String> value = text(node, field);
      if (value.isPresent()) {
        return value;
      }
    }
    return Optional.empty();
  }

  private static Optional<String> text(JsonNode node, String field) {
    if (node == null || !node.isObject()) {
      return Optional.empty();
    }
    JsonNode child = node.get(field);
    if (child != null && child.isTextual()) {
      return Optional.of(child.asText());
    }
    return Optional.empty();
  }

  private static SourceRecordUsage usage(JsonNode node) {
    if (node == null || !node.isObject()) {
      return SourceRecordUsage.empty();
    }
    JsonNode usage = node.get("usage");
    if (usage == null || !usage.isObject()) {
      return SourceRecordUsage.empty();
    }
    return new SourceRecordUsage(
        number(usage, "input_tokens"),
        number(usage, "cache_read_input_tokens"),
        number(usage, "cache_creation_input_tokens"),
        number(usage, "output_tokens"));
  }

  private static long number(JsonNode node, String field) {
    JsonNode child = node.get(field);
    return child != null && child.isNumber() ? child.asLong() : 0L;
  }

  private static List<SourceToolCall> toolCalls(JsonNode node) {
    if (node == null || !node.isObject()) {
      return List.of();
    }
    JsonNode content = node.get("content");
    if (content == null || !content.isArray()) {
      return List.of();
    }
    List<SourceToolCall> calls = new ArrayList<>();
    for (JsonNode block : content) {
      if ("tool_use".equals(text(block, "type").orElse(""))) {
        Optional<String> id = text(block, "id");
        Optional<String> name = text(block, "name");
        if (id.isPresent() && name.isPresent()) {
          calls.add(new SourceToolCall(id.get(), name.get()));
        }
      }
    }
    return List.copyOf(calls);
  }
}
