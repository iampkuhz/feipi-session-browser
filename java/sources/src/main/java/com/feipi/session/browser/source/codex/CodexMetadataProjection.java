package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderResult;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

/** discovery 专用证据视图；不改变 parse 正文或原文件。 */
final class CodexMetadataProjection {
  // metadata 消费端只读此占位；共享节点仍为每条物理事件保留一个 list 位置。
  private static final ObjectNode EMPTY_EVENT = JsonNodeFactory.instance.objectNode();

  private CodexMetadataProjection() {}

  static JsonlReaderResult read(JsonlReader reader, Path path) throws IOException {
    return reader.readPreprojected(
        path, CodexEventProjection.preparseRules(), CodexMetadataProjection::project);
  }

  static JsonNode project(JsonNode event) {
    JsonNode payload = event.path("payload");
    String type = event.path("type").asText();
    String subtype = payload.path("type").asText();
    boolean usage =
        "token_usage_record".equals(type)
            || ("event_msg".equals(type) && "token_count".equals(subtype));
    boolean boundary =
        "turn_context".equals(type) || ("event_msg".equals(type) && "task_started".equals(subtype));
    boolean spawnCall =
        ("function_call".equals(subtype) || "custom_tool_call".equals(subtype))
            && "spawn_agent".equals(payload.path("name").asText());
    boolean toolOutput =
        "function_call_output".equals(subtype) || "custom_tool_call_output".equals(subtype);
    JsonNode output =
        toolOutput ? CodexSourceAdapter.metadataSpawnOutput(payload.get("output")) : null;
    boolean metadata = "session_meta".equals(type);
    if (!usage
        && !boundary
        && !metadata
        && !spawnCall
        && (output == null || output.isEmpty())
        && !event.has("ordinal")) {
      return EMPTY_EVENT;
    }
    ObjectNode result = JsonNodeFactory.instance.objectNode();
    copy(event, result, List.of("type", "ordinal"));
    ObjectNode projected = result.putObject("payload");
    copy(payload, projected, List.of("type", "turn_id"));
    if (metadata) {
      copy(
          payload,
          projected,
          List.of("id", "parent_thread_id", "forked_from_id", "subagent_history_start_ordinal"));
      JsonNode parent =
          payload.path("source").path("subagent").path("thread_spawn").path("parent_thread_id");
      if (parent.isTextual()) {
        projected
            .putObject("source")
            .putObject("subagent")
            .putObject("thread_spawn")
            .set("parent_thread_id", parent);
      }
    }
    if ("token_usage_record".equals(type)) {
      copy(payload, projected, List.of("response_id", "usage", "thread_token_usage"));
    } else if ("event_msg".equals(type) && "token_count".equals(subtype)) {
      copy(payload, projected, List.of("total_token_usage", "last_token_usage"));
      if (payload.path("info").isObject()) {
        copy(
            payload.path("info"),
            projected.putObject("info"),
            List.of("total_token_usage", "last_token_usage"));
      }
    }
    if ("function_call".equals(subtype)
        || "custom_tool_call".equals(subtype)
        || "function_call_output".equals(subtype)
        || "custom_tool_call_output".equals(subtype)) {
      copy(payload, projected, List.of("call_id", "name"));
      if ("function_call_output".equals(subtype) || "custom_tool_call_output".equals(subtype)) {
        // 所有结果只保身份，随后既有双遍关联按精确 call_id 筛选，兼容结果先于声明。
        projected.set("output", output);
      }
    }
    return result;
  }

  private static void copy(JsonNode source, ObjectNode target, List<String> fields) {
    for (String field : fields) {
      JsonNode value = source.get(field);
      if (value != null) target.set(field, value);
    }
  }
}
