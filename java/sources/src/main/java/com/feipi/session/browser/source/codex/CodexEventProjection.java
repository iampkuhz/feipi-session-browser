package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.source.common.JsonlPreprojection;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderResult;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;
import java.util.function.UnaryOperator;

/** 仅投影 Codex 当前不消费的非文本和历史快照字段；原始来源按 locator 保留。 */
final class CodexEventProjection implements UnaryOperator<JsonNode> {
  private static final Set<String> IMAGE_TYPES =
      Set.of("input_image", "output_image", "image", "image_url");

  private int removedImages;
  private int removedStructures;

  static JsonlReaderResult read(JsonlReader reader, Path path) throws IOException {
    return readTo(reader, path, null);
  }

  static JsonlReaderResult readTo(JsonlReader reader, Path path, List<JsonNode> sink)
      throws IOException {
    var projection = new CodexEventProjection();
    var result =
        sink == null
            ? reader.readPreprojected(path, preparseRules(), projection)
            : reader.readPreprojectedTo(path, preparseRules(), projection, sink);
    if (projection.removedImages == 0 && projection.removedStructures == 0) {
      return result;
    }
    var diagnostics = new ArrayList<>(result.diagnostics());
    diagnostics.add(
        new SourceDiagnostic(
            ParseSeverity.INFO,
            ParseIssueType.NON_OBJECT_SKIPPED,
            "Normalized event projection retains text and source identity; "
                + projection.removedImages
                + " non-text image fields and "
                + projection.removedStructures
                + " opaque or historical snapshot fields remain available only in the unchanged raw"
                + " source",
            1,
            Optional.empty(),
            "CODEX_NON_TEXT_PAYLOAD_PROJECTED",
            path.toString(),
            OptionalInt.empty(),
            OptionalInt.empty(),
            OptionalInt.empty()));
    return new JsonlReaderResult(
        result.events(), diagnostics, result.stats(), result.stoppedByLimit());
  }

  static List<JsonlPreprojection.Rule> preparseRules() {
    var rules = new ArrayList<JsonlPreprojection.Rule>();
    rules.add(
        new JsonlPreprojection.Rule("payload.replacement_history", "compacted", "", Set.of()));
    rules.add(new JsonlPreprojection.Rule("payload.item", "event_msg", "item_completed", Set.of()));
    rules.add(
        new JsonlPreprojection.Rule(
            "payload.encrypted_content", "response_item", "reasoning", Set.of()));
    for (String field : Set.of("image_url", "data", "url")) {
      rules.add(
          new JsonlPreprojection.Rule(
              "payload.content.[]." + field, "response_item", "message", IMAGE_TYPES));
      for (String type : Set.of("function_call_output", "custom_tool_call_output")) {
        rules.add(
            new JsonlPreprojection.Rule(
                "payload.output.[]." + field, "response_item", type, IMAGE_TYPES));
      }
    }
    return List.copyOf(rules);
  }

  @Override
  public JsonNode apply(JsonNode event) {
    if (!(event.path("payload") instanceof ObjectNode payload)) {
      return event;
    }
    String type = event.path("type").asText();
    String subtype = payload.path("type").asText();
    if ("compacted".equals(type)) {
      removeStructure(payload, "replacement_history");
    } else if ("event_msg".equals(type) && "item_completed".equals(subtype)) {
      removeStructure(payload, "item");
    } else if ("response_item".equals(type)) {
      if ("reasoning".equals(subtype)) {
        removeStructure(payload, "encrypted_content");
      }
      if ("message".equals(subtype)) {
        projectImages(payload.get("content"));
      } else if ("function_call_output".equals(subtype)
          || "custom_tool_call_output".equals(subtype)) {
        projectImages(payload.get("output"));
      }
    }
    return event;
  }

  private void removeStructure(ObjectNode payload, String field) {
    if (payload.remove(field) != null) {
      removedStructures++;
    }
  }

  private void projectImages(JsonNode root) {
    if (root == null) {
      return;
    }
    var pending = new ArrayDeque<JsonNode>();
    pending.add(root);
    while (!pending.isEmpty()) {
      JsonNode node = pending.removeFirst();
      if (node instanceof ObjectNode object && IMAGE_TYPES.contains(node.path("type").asText())) {
        for (String field : Set.of("image_url", "data", "url")) {
          if (object.remove(field) != null) {
            removedImages++;
          }
        }
      }
      if (node.isArray()) {
        node.elements().forEachRemaining(pending::addLast);
      }
    }
  }
}
