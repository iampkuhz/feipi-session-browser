package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;

/** 只识别已完整读取、仅含启动记录的分页侧聊；遇到其他事件保留会话。 */
final class CodexEmptySideChat {
  private CodexEmptySideChat() {}

  static boolean matches(CodexEventBatch batch) {
    var result = batch.result();
    var events = batch.events();
    if (result.stoppedByLimit() || !result.diagnostics().isEmpty() || events.size() < 2)
      return false;
    var header = events.getFirst();
    String parent = paginatedParent(header);
    if (parent.isEmpty() || !CodexSideContext.isStartupOnlyBoundary(events.getLast(), parent)) {
      return false;
    }
    long start = header.path("ordinal").asLong();
    int last = events.size() - 1;
    for (int i = 1; i <= last; i++) {
      var event = events.get(i);
      var ordinal = event.path("ordinal");
      if (!ordinal.isIntegralNumber()
          || !ordinal.canConvertToLong()
          || ordinal.asLong() != start + i
          || (i < last && !isInitialization(event))) return false;
    }
    return true;
  }

  private static String paginatedParent(JsonNode header) {
    var meta = header.path("payload");
    String parent = meta.path("forked_from_id").asText("");
    var history = meta.path("history_base");
    var start = header.path("ordinal");
    var bytes = history.path("end_byte_offset");
    if (!"session_meta".equals(header.path("type").asText())
        || !meta.path("attached_thread").isBoolean()
        || !meta.path("attached_thread").booleanValue()
        || !"paginated".equals(meta.path("history_mode").asText())
        || !meta.path("forked_from_id").isTextual()
        || parent.isBlank()
        || !meta.path("id").isTextual()
        || meta.path("id").asText("").isBlank()
        || parent.equals(meta.path("id").asText())
        || !history.path("thread_id").isTextual()
        || !parent.equals(history.path("thread_id").asText())
        || !start.isIntegralNumber()
        || !start.canConvertToInt()
        || start.asInt() <= 0
        || !start.equals(meta.path("forked_from_ordinal_exclusive"))
        || !start.equals(history.path("end_ordinal_exclusive"))
        || !bytes.isIntegralNumber()
        || !bytes.canConvertToLong()
        || bytes.asLong() <= 0) return "";
    return parent;
  }

  private static boolean isInitialization(JsonNode event) {
    var payload = event.path("payload");
    String subtype = payload.path("type").asText();
    return switch (event.path("type").asText()) {
      case "event_msg" ->
          "thread_settings_applied".equals(subtype)
              || ("turn_aborted".equals(subtype)
                  && "interrupted".equals(payload.path("reason").asText()));
      case "response_item" ->
          "message".equals(subtype) && "developer".equals(payload.path("role").asText());
      default -> false;
    };
  }
}
