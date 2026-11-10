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
  static final String PARENT_CONFLICT = "CODEX_HISTORY_PARENT_CONFLICT";
  private final List<JsonNode> events;
  private final int start;
  private final String inheritedModel;
  private final boolean inheritedUsage;

  private CodexActivityRange(
      List<JsonNode> source, int start, String inheritedModel, boolean inheritedUsage) {
    this.start = start;
    this.inheritedModel = inheritedModel;
    this.inheritedUsage = inheritedUsage;
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
      return new CodexActivityRange(source, 0, "", false);
    }
    if (diagnostics.stream().anyMatch(d -> !"CODEX_NON_TEXT_PAYLOAD_PROJECTED".equals(d.code()))) {
      throw new InvalidHistoryException(
          "CODEX_HISTORY_READER_INCOMPLETE", "history reader evidence is incomplete");
    }
    JsonNode first = source.getFirst();
    JsonNode header = first.path("payload");
    boolean paginated = "paginated".equals(header.path("history_mode").asText());
    JsonNode boundary = header.path("subagent_history_start_ordinal");
    if (!boundary.isIntegralNumber()
        || !boundary.canConvertToInt()
        || boundary.intValue() < (paginated ? 1 : 2)
        || boundary.intValue() > source.size()) {
      throw new InvalidHistoryException(
          "CODEX_HISTORY_BOUNDARY_INVALID", "boundary is outside the source");
    }
    int start = boundary.intValue();
    String model = "";
    boolean inheritedUsage = false;
    for (int index = 0; index < source.size(); index++) {
      JsonNode event = source.get(index);
      JsonNode ordinal = event.path("ordinal");
      if (!ordinal.isIntegralNumber()
          || !ordinal.canConvertToInt()
          || ordinal.intValue() != index) {
        throw new InvalidHistoryException(
            "CODEX_HISTORY_ORDINAL_INVALID", "ordinal evidence is not continuous");
      }
      if (index >= start) continue;
      String type = event.path("type").asText();
      if ("token_usage_record".equals(type)
          || ("event_msg".equals(type)
              && "token_count".equals(event.path("payload").path("type").asText()))) {
        inheritedUsage = true;
      }
      JsonNode candidate = event.path("payload").path("model");
      if (candidate.isTextual() && !candidate.asText().isBlank()) model = candidate.asText();
    }
    validateIdentity(first, source, paginated);
    if (inheritedUsage && !paginated) {
      throw new InvalidHistoryException(
          "CODEX_HISTORY_USAGE_UNSUPPORTED", "inherited usage counter lineage is unknown");
    }
    return new CodexActivityRange(source, start, model, inheritedUsage);
  }

  private static void validateIdentity(JsonNode first, List<JsonNode> source, boolean paginated)
      throws InvalidHistoryException {
    JsonNode header = first.path("payload");
    String child = header.path("id").asText("");
    String directParent = header.path("parent_thread_id").asText("");
    String nestedParent =
        header
            .path("source")
            .path("subagent")
            .path("thread_spawn")
            .path("parent_thread_id")
            .asText("");
    if (!"session_meta".equals(first.path("type").asText())
        || !header.path("id").isTextual()
        || child.isBlank()) {
      throw new InvalidHistoryException(PARENT_CONFLICT, "event[0] requires session_meta with id");
    }
    if (!directParent.isBlank() && !nestedParent.isBlank() && !directParent.equals(nestedParent)) {
      throw new InvalidHistoryException(
          PARENT_CONFLICT, "event[0] direct and nested parent_thread_id disagree");
    }
    String parent = directParent.isBlank() ? nestedParent : directParent;
    String forkParent = header.path("forked_from_id").asText("");
    if (child.equals(parent) || child.equals(forkParent)) {
      throw new InvalidHistoryException(PARENT_CONFLICT, "event[0] parent or fork points to self");
    }
    // Codex 的分页迁移只保留 ordinal 0 的 canonical session_meta，spawn parent 与 fork 来源不是同一字段。
    if (paginated) return;
    if (parent.isBlank() || !parent.equals(forkParent)) {
      throw new InvalidHistoryException(
          PARENT_CONFLICT, "event[0] parent_thread_id and forked_from_id missing or inconsistent");
    }
    JsonNode copied = source.get(1);
    if (!"session_meta".equals(copied.path("type").asText())
        || !parent.equals(copied.path("payload").path("id").asText(""))) {
      throw new InvalidHistoryException(
          PARENT_CONFLICT, "event[1] copied parent session_meta missing or inconsistent");
    }
  }

  /** 继承历史校验失败，携带与异常文本无关的稳定错误码。 */
  static final class InvalidHistoryException extends IOException {
    private static final long serialVersionUID = 1L;
    private final String code;

    InvalidHistoryException(String code, String detail) {
      super(code + ": " + detail);
      this.code = code;
    }

    String code() {
      return code;
    }
  }

  List<JsonNode> events() {
    return events;
  }

  int start() {
    return start;
  }

  boolean inheritedUsage() {
    return inheritedUsage;
  }

  String initialModel(String fallback) {
    return inheritedModel.isBlank() ? fallback : inheritedModel;
  }
}
