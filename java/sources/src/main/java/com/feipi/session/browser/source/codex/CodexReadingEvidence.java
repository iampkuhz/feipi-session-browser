package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceReadingEvidence;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.List;

/** 源事件上有明确角色或字段的阅读证据；不保存压缩的整份 replacement_history。 */
final class CodexReadingEvidence {
  private CodexReadingEvidence() {}

  static void collect(JsonNode event, SourceRecord owner, List<SourceReadingEvidence> evidence) {
    var payload = event.path("payload");
    switch (event.path("type").asText()) {
      case "session_meta" -> {
        var base = payload.path("base_instructions").path("text").asText("");
        var instructions = payload.path("instructions").asText("");
        add(evidence, "base", base);
        if (!base.equals(instructions)) add(evidence, "session", instructions);
        for (String field : List.of("model_provider", "source", "originator", "cli_version")) {
          var value = payload.path(field);
          add(evidence, field, value.isObject() ? value.toString() : value.asText(""));
        }
        tools(payload, evidence, "session_");
      }
      case "turn_context" -> {
        tools(payload, evidence, "");
        var instructions =
            payload.path("collaboration_mode").path("settings").path("developer_instructions");
        if (instructions.isTextual() && !instructions.asText().isBlank()) {
          add(evidence, "collaboration_instructions", instructions.asText());
        } else if (instructions.isTextual() || instructions.isNull()) {
          add(evidence, "collaboration_clear", "clear");
        }
      }
      case "token_usage_record" -> {
        usage(payload.path("usage"), owner, evidence);
        if (confirmedResponse(owner)) {
          add(evidence, "response_usage", "observed");
          Long turnTotal =
              CodexTokenProvenance.readUsageLong(
                  payload.path("turn_token_usage"), List.of("total_tokens"));
          if (turnTotal != null) add(evidence, "turn_total_tokens", turnTotal.toString());
        }
      }
      case "event_msg" -> {
        if ("token_count".equals(payload.path("type").asText())) {
          var last = payload.path("info").path("last_token_usage");
          usage(last.isObject() ? last : payload.path("last_token_usage"), owner, evidence);
        }
      }
      case "compacted" ->
          add(
              evidence,
              "boundary",
              payload.path(CodexEventProjection.PROJECTED_HISTORY_FIELD).asBoolean()
                  ? "replacement_history"
                  : "compacted");
      case "response_item" -> {
        String type = payload.path("type").asText();
        String role = payload.path("role").asText();
        if ("additional_tools".equals(type) && "developer".equals(role)) {
          toolDefinitions(payload.path("tools"), evidence, "additional_tools");
        }
        if (!"message".equals(type)) return;
        if ("developer".equals(role) || "system".equals(role)) {
          add(evidence, role, CodexSourceAdapter.responseText(payload.get("content")));
        }
      }
      default -> {}
    }
  }

  static void followingCompaction(
      JsonNode response, JsonNode next, SourceRecord owner, List<SourceReadingEvidence> evidence) {
    if (!confirmedResponse(owner) || !"compacted".equals(next.path("type").asText())) return;
    var ordinal = response.path("ordinal");
    var nextOrdinal = next.path("ordinal");
    if (ordinal.canConvertToInt()
        && nextOrdinal.canConvertToInt()
        && ordinal.longValue() + 1 != nextOrdinal.longValue()) return;
    var source = response.path("payload");
    var compacted = next.path("payload");
    if (conflicts(source, compacted, "turn_id") || conflicts(source, compacted, "response_id"))
      return;
    String compactionResponse = compacted.path("compaction_response_id").asText("");
    if (!compactionResponse.isBlank()) {
      if (!compactionResponse.equals(source.path("response_id").asText(""))) return;
      add(evidence, "response_compaction", "identity");
    } else {
      add(evidence, "response_compaction", "adjacent");
    }
  }

  private static boolean confirmedResponse(SourceRecord owner) {
    return "assistant".equals(owner.eventType())
        && owner.callId().filter(id -> id.startsWith("token_usage_record:")).isPresent()
        && "provider_reported".equals(owner.usage().provenance().get("outputTokenPrecision"));
  }

  private static boolean conflicts(JsonNode first, JsonNode next, String field) {
    String firstValue = first.path(field).asText("");
    String nextValue = next.path(field).asText("");
    return !firstValue.isBlank() && !nextValue.isBlank() && !firstValue.equals(nextValue);
  }

  private static void usage(
      JsonNode usage, SourceRecord owner, List<SourceReadingEvidence> evidence) {
    if (!"assistant".equals(owner.eventType())
        || owner.callId().filter(id -> id.startsWith("token_")).isEmpty()) return;
    Long input =
        CodexTokenProvenance.readUsageLong(
            usage, List.of("input_tokens", "inputTokens", "prompt_tokens"));
    long accountedInput =
        owner.usage().inputTokens()
            + owner.usage().cacheReadInputTokens()
            + owner.usage().cacheCreationInputTokens();
    if (input != null && input == accountedInput) add(evidence, "input_tokens", input.toString());
    Long output =
        CodexTokenProvenance.readUsageLong(
            usage, List.of("output_tokens", "outputTokens", "completion_tokens"));
    if (output != null && output == owner.usage().outputTokens()) {
      add(evidence, "output_tokens", output.toString());
    }
    Long total = CodexTokenProvenance.readUsageLong(usage, List.of("total_tokens"));
    if (total != null && total == owner.usage().total()) {
      add(evidence, "total_tokens", total.toString());
    }
    Long reasoning =
        CodexTokenProvenance.readUsageLong(
            usage, List.of("reasoning_output_tokens", "reasoning_tokens"));
    if (reasoning == null) {
      reasoning =
          CodexTokenProvenance.readUsageLong(
              usage.path("output_tokens_details"), List.of("reasoning_tokens"));
    }
    if (output != null
        && output == owner.usage().outputTokens()
        && reasoning != null
        && reasoning <= output) {
      add(evidence, "reasoning_tokens", reasoning.toString());
    }
  }

  private static void tools(JsonNode payload, List<SourceReadingEvidence> evidence, String prefix) {
    for (String field : List.of("dynamic_tools", "additional_tools")) {
      toolDefinitions(payload.path(field), evidence, prefix + field);
    }
  }

  private static void toolDefinitions(
      JsonNode tools, List<SourceReadingEvidence> evidence, String kind) {
    if ((tools.isArray() || tools.isObject()) && !tools.isEmpty()) {
      add(evidence, kind, tools.toPrettyString());
    }
  }

  private static void add(List<SourceReadingEvidence> evidence, String kind, String value) {
    if (!value.isBlank()) evidence.add(new SourceReadingEvidence(kind, value));
  }
}
