package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceCollaborationEvidence;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** 只识别已确认的委派、等待与限定 namespace 追加输入协议，不解析通知文本或推断消息投递。 */
final class CodexCollaborationFacts {
  private static final int MAX_PROTOCOL_CHARS = 1024 * 1024;
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private final Map<String, String> kinds = new HashMap<>();
  private final Map<String, Input> inputs = new HashMap<>();
  private final Map<String, Receipt> receipts = new HashMap<>();
  private final Set<String> receiptConflicts = new HashSet<>();
  private final Map<String, String> delegateTargets = new HashMap<>();
  private final Set<String> conflicts = new HashSet<>();
  private final Map<String, SourceRecordRelation> relations;

  CodexCollaborationFacts(List<JsonNode> events, Map<String, SourceRecordRelation> relations) {
    this.relations = relations;
    var declarations = new HashSet<String>();
    for (var event : events) {
      var p = event.path("payload");
      String type = p.path("type").asText();
      String name = p.path("name").asText();
      String id = p.path("call_id").asText();
      if (!Set.of("function_call", "custom_tool_call").contains(type)) continue;
      if (!declarations.add(id)) conflicts.add(id);
      if (Set.of("spawn_agent", "wait_agent").contains(name)) {
        kinds.putIfAbsent(id, name.equals("spawn_agent") ? "delegate" : "wait");
      } else if ("function_call".equals(type)
          && "multi_agent_v1".equals(p.path("namespace").asText())
          && "send_input".equals(name)) {
        kinds.putIfAbsent(id, "input");
        inputs.putIfAbsent(id, input(p.get("arguments")));
      }
    }
    for (var event : events) {
      var p = event.path("payload");
      String id = p.path("call_id").asText();
      if (!"input".equals(kinds.get(id)) || !p.path("type").asText().endsWith("_output")) continue;
      var receipt = receipt(p);
      var previous = receipts.putIfAbsent(id, receipt);
      if (previous != null && !previous.equals(receipt)) receiptConflicts.add(id);
    }
    for (var event : events) {
      var p = event.path("payload");
      String id = p.path("call_id").asText();
      if (!"delegate".equals(kinds.get(id)) || !p.has("output")) continue;
      String target = json(p.get("output")).path("agent_id").asText("");
      if (!target.isBlank()) {
        var previous = delegateTargets.putIfAbsent(id, target);
        if (previous != null && !previous.equals(target)) conflicts.add(id);
      }
    }
  }

  List<SourceCollaborationEvidence> forEvent(JsonNode event, SourceRecord record) {
    var p = event.path("payload");
    String id = p.path("call_id").asText();
    String kind = kinds.get(id);
    if (kind == null) return List.of();
    boolean result = "tool_result".equals(record.eventType());
    if (!result && !"tool_use".equals(record.eventType())) return List.of();
    String phase = result ? "result_report" : "declaration";
    if (conflicts.contains(id))
      return List.of(fact(id, kind, phase, "", "", "conflicting_tool_identity"));
    if (id.length() > 4096)
      return List.of(fact(id, kind, phase, "", "", "identity_resource_limit"));
    if ("input".equals(kind)) {
      var input = inputs.get(id);
      if (!result) return List.of(fact(id, kind, phase, input.target(), "", input.reason()));
      var receipt = receipt(p);
      String reason = receiptConflicts.contains(id) ? "conflicting_report" : receipt.reason();
      return List.of(
          fact(
              id,
              kind,
              phase,
              input.target(),
              "queued".equals(reason) && "explicit_target".equals(input.reason()) ? "queued" : "",
              "explicit_target".equals(input.reason()) ? reason : input.reason()));
    }
    JsonNode raw = p.get(result ? "output" : "arguments");
    if (raw != null
        && raw.isTextual()
        && raw.textValue().length() > MAX_PROTOCOL_CHARS
        && (result || "wait".equals(kind)))
      return List.of(fact(id, kind, phase, "", "", "protocol_payload_resource_limit"));
    JsonNode body = "wait".equals(kind) ? json(raw) : MAPPER.createObjectNode();
    List<SourceCollaborationEvidence> facts = new ArrayList<>();
    if ("delegate".equals(kind)) {
      String target = delegateTargets.getOrDefault(id, "");
      if (target.isBlank() && relations.containsKey("tool:" + id))
        target = relations.get("tool:" + id).subagentId().orElse("");
      facts.add(
          fact(
              id,
              kind,
              phase,
              target,
              "",
              target.isBlank()
                  ? "target_unknown"
                  : !relations.containsKey("tool:" + id)
                      ? "child_link_conflict"
                      : relations.get("tool:" + id).parentThreadId().isPresent()
                          ? "child_candidate_available"
                          : "child_not_found"));
    } else if (result && body.path("status").isObject()) {
      var entries = body.path("status").fields();
      while (entries.hasNext() && facts.size() < 127) {
        var entry = entries.next();
        String status = "";
        for (String key : List.of("completed", "running", "pending", "errored", "not_found")) {
          if (entry.getValue().has(key)) status = status.isEmpty() ? key : "conflicting_report";
        }
        String reason =
            "conflicting_report".equals(status)
                ? "conflicting_report"
                : status.isBlank() ? "report_status_unknown" : "explicit_report";
        facts.add(
            fact(
                id,
                kind,
                phase,
                entry.getKey(),
                "conflicting_report".equals(status) ? "" : status,
                reason));
      }
      if (entries.hasNext()) facts.add(fact(id, kind, phase, "", "", "targets_truncated"));
    } else if (!result && body.path("targets").isArray()) {
      for (var target : body.path("targets")) {
        if (facts.size() == 127) {
          facts.add(fact(id, kind, phase, "", "", "targets_truncated"));
          break;
        }
        if (target.isTextual() && !target.asText().isBlank())
          facts.add(fact(id, kind, phase, target.asText(), "", "explicit_target"));
      }
    }
    if (facts.isEmpty()) facts.add(fact(id, kind, phase, "", "", "target_unknown"));
    return List.copyOf(facts);
  }

  private static Input input(JsonNode raw) {
    if (oversized(raw)) return new Input("", "protocol_payload_resource_limit");
    var body = json(raw);
    String target = body.path("target").isTextual() ? body.path("target").asText() : "";
    if (target.length() > 4096) return new Input("", "identity_resource_limit");
    try {
      if (!java.util.UUID.fromString(target).toString().equalsIgnoreCase(target))
        return new Input("", "invalid_target");
    } catch (IllegalArgumentException ignored) {
      return new Input("", "invalid_target");
    }
    boolean message = body.path("message").isTextual() && !body.path("message").asText().isBlank();
    boolean items = body.path("items").isArray() && !body.path("items").isEmpty();
    if ((body.hasNonNull("message") && body.hasNonNull("items"))
        || (!message && !items)
        || (body.has("interrupt") && !body.path("interrupt").isBoolean()))
      return new Input(target, "invalid_input");
    if (items) {
      if (body.path("items").size() > 1024)
        return new Input(target, "protocol_payload_resource_limit");
      for (var item : body.path("items")) {
        List<String> required =
            switch (item.path("type").asText()) {
              case "text" -> List.of("text");
              case "image" -> List.of("image_url");
              case "audio" -> List.of("audio_url");
              case "local_image", "local_audio" -> List.of("path");
              case "skill", "mention" -> List.of("name", "path");
              default -> List.of("unknown");
            };
        if (required.stream().anyMatch(field -> !item.path(field).isTextual()))
          return new Input(target, "invalid_input");
      }
    }
    return new Input(target, "explicit_target");
  }

  private static Receipt receipt(JsonNode payload) {
    if (!"function_call_output".equals(payload.path("type").asText())
        || (payload.has("namespace")
            && !"multi_agent_v1".equals(payload.path("namespace").asText()))
        || (payload.has("name") && !"send_input".equals(payload.path("name").asText())))
      return new Receipt("", "conflicting_report");
    var raw = payload.get("output");
    if (oversized(raw)) return new Receipt("", "protocol_payload_resource_limit");
    var body = json(raw);
    if (explicitError(payload) || explicitError(body)) return new Receipt("", "explicit_error");
    var id = body.path("submission_id");
    if (!id.isTextual() || id.asText().isBlank()) return new Receipt("", "report_status_unknown");
    if (id.asText().length() > 4096) return new Receipt("", "identity_resource_limit");
    return new Receipt(id.asText(), "queued");
  }

  private static boolean explicitError(JsonNode body) {
    var error = body.path("error");
    return (body.path("is_error").isBoolean() && body.path("is_error").asBoolean())
        || error.isObject()
        || (error.isTextual() && !error.asText().isBlank());
  }

  private static boolean oversized(JsonNode raw) {
    return raw != null
        && (raw.isTextual() ? raw.textValue().length() : raw.toString().length())
            > MAX_PROTOCOL_CHARS;
  }

  /**
   * 已核声明的紧凑目标，不保存输入正文。
   *
   * @param target 完整目标实例
   * @param reason 核验或未知原因
   */
  private record Input(String target, String reason) {}

  /**
   * 仅用于检测同工具冲突的有限回执，不是消息生命周期。
   *
   * @param id 提交标识
   * @param reason 工具结果的证据类别
   */
  private record Receipt(String id, String reason) {}

  private static SourceCollaborationEvidence fact(
      String id, String kind, String phase, String target, String status, String reason) {
    if (target.length() > 4096)
      return new SourceCollaborationEvidence(
          id, kind, phase, Optional.empty(), Optional.empty(), "identity_resource_limit");
    return new SourceCollaborationEvidence(
        id, kind, phase, optional(target), optional(status), reason);
  }

  private static Optional<String> optional(String value) {
    return value.isBlank() ? Optional.empty() : Optional.of(value);
  }

  private static JsonNode json(JsonNode node) {
    if (node == null) return MAPPER.createObjectNode();
    if (!node.isTextual()) return node;
    if (node.textValue().length() > MAX_PROTOCOL_CHARS) return MAPPER.createObjectNode();
    try {
      JsonNode parsed = MAPPER.readTree(node.asText());
      return parsed == null ? MAPPER.createObjectNode() : parsed;
    } catch (IOException e) {
      return MAPPER.createObjectNode();
    }
  }
}
