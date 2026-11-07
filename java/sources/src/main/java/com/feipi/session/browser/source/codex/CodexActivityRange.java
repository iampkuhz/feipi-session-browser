package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.IOException;
import java.util.AbstractList;
import java.util.List;

/** 借用事件列表的活动范围；屏蔽继承证据但不重编号原始事件。 */
final class CodexActivityRange {
  private static final JsonNode CONTEXT = JsonNodeFactory.instance.objectNode();
  private final List<JsonNode> events;
  private final int start;
  private final String inheritedModel;

  private CodexActivityRange(List<JsonNode> source, int start, String inheritedModel) {
    this.start = start;
    this.inheritedModel = inheritedModel;
    this.events =
        start == 0
            ? source
            : new AbstractList<>() {
              @Override
              public JsonNode get(int index) {
                java.util.Objects.checkIndex(index, source.size());
                return index < start ? CONTEXT : source.get(index);
              }

              @Override
              public int size() {
                return source.size();
              }
            };
  }

  static CodexActivityRange create(List<JsonNode> source, List<SourceDiagnostic> diagnostics)
      throws IOException {
    if (source.isEmpty()
        || !source.getFirst().path("payload").has("subagent_history_start_ordinal")) {
      return new CodexActivityRange(source, 0, "");
    }
    if (diagnostics.stream().anyMatch(d -> !"CODEX_NON_TEXT_PAYLOAD_PROJECTED".equals(d.code()))) {
      throw new IOException("CODEX_HISTORY_INVALID: history reader evidence is incomplete");
    }
    JsonNode first = source.getFirst();
    JsonNode header = first.path("payload");
    JsonNode boundary = header.path("subagent_history_start_ordinal");
    if (!boundary.isIntegralNumber()
        || !boundary.canConvertToInt()
        || boundary.intValue() < 2
        || boundary.intValue() > source.size()) {
      throw new IOException("CODEX_HISTORY_INVALID: boundary is outside the source");
    }
    int start = boundary.intValue();
    String child = header.path("id").asText("");
    String parent = header.path("parent_thread_id").asText("");
    String nestedParent =
        header
            .path("source")
            .path("subagent")
            .path("thread_spawn")
            .path("parent_thread_id")
            .asText("");
    if (parent.isBlank()) {
      parent = nestedParent;
    }
    if (!"session_meta".equals(first.path("type").asText())
        || child.isBlank()
        || parent.isBlank()
        || child.equals(parent)
        || (!nestedParent.isBlank() && !parent.equals(nestedParent))
        || !parent.equals(header.path("forked_from_id").asText(""))
        || !"session_meta".equals(source.get(1).path("type").asText())
        || !parent.equals(source.get(1).path("payload").path("id").asText(""))) {
      throw new IOException("CODEX_HISTORY_INVALID: parent identity evidence conflicts");
    }
    String model = "";
    for (int index = 0; index < source.size(); index++) {
      JsonNode event = source.get(index);
      JsonNode ordinal = event.path("ordinal");
      if (!ordinal.isIntegralNumber()
          || !ordinal.canConvertToInt()
          || ordinal.intValue() != index) {
        throw new IOException("CODEX_HISTORY_INVALID: ordinal evidence is not continuous");
      }
      if (index >= start) continue;
      String type = event.path("type").asText();
      if ("token_usage_record".equals(type)
          || ("event_msg".equals(type)
              && "token_count".equals(event.path("payload").path("type").asText()))) {
        throw new IOException(
            "CODEX_HISTORY_USAGE_UNSUPPORTED: inherited usage counter lineage is unknown");
      }
      JsonNode candidate = event.path("payload").path("model");
      if (candidate.isTextual() && !candidate.asText().isBlank()) model = candidate.asText();
    }
    return new CodexActivityRange(source, start, model);
  }

  List<JsonNode> events() {
    return events;
  }

  int start() {
    return start;
  }

  String initialModel(String fallback) {
    return inheritedModel.isBlank() ? fallback : inheritedModel;
  }
}
