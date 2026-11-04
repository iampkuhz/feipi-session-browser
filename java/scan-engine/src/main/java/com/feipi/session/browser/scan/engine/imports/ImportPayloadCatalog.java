package com.feipi.session.browser.scan.engine.imports;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** 保存完整原始事件和独立工具结果；不改变共享归一化的计量或调用归属。 */
final class ImportPayloadCatalog {
  private static final ObjectMapper MAPPER = new ObjectMapper();

  private ImportPayloadCatalog() {}

  static Map<String, SourceUnitCatalogEntry> read(Path file, String logicalPath)
      throws IOException {
    Map<String, SourceUnitCatalogEntry> catalog = new LinkedHashMap<>();
    try (var lines = Files.newBufferedReader(file)) {
      String line;
      int index = 0;
      while ((line = lines.readLine()) != null) {
        if (index == 0 && line.startsWith("\uFEFF")) {
          line = line.substring(1);
        }
        if (line.isBlank()) {
          continue;
        }
        JsonNode event = MAPPER.readTree(line);
        String key = logicalPath + "#raw[" + index + "]";
        put(catalog, entry(key, logicalPath, "import_raw_event", index, "", "", line));
        int part = 0;
        for (JsonNode block : contentBlocks(event)) {
          if ("tool_result".equals(block.path("type").asText())) {
            String id =
                block
                    .path("tool_use_id")
                    .asText(block.path("call_id").asText(block.path("id").asText()));
            put(
                catalog,
                entry(
                    key + "/result/" + part,
                    logicalPath,
                    "tool_result",
                    index,
                    id,
                    resultText(block),
                    block.toString()));
          } else if ("tool_use".equals(block.path("type").asText())) {
            declaration(catalog, key + "/tool/" + part, logicalPath, index, block);
          }
          part++;
        }
        JsonNode payload = event.path("payload");
        if (List.of("function_call", "custom_tool_call").contains(payload.path("type").asText())) {
          declaration(catalog, key + "/tool", logicalPath, index, payload);
        }
        if (List.of("function_call_output", "custom_tool_call_output")
            .contains(payload.path("type").asText())) {
          put(
              catalog,
              entry(
                  key + "/result",
                  logicalPath,
                  "tool_result",
                  index,
                  payload.path("call_id").asText(),
                  text(payload.path("output")),
                  payload.toString()));
        }
        index++;
      }
    }
    return Collections.unmodifiableMap(catalog);
  }

  private static List<JsonNode> contentBlocks(JsonNode event) {
    var blocks = new LinkedHashSet<JsonNode>();
    for (JsonNode owner : List.of(event, event.path("message"), event.path("payload"))) {
      for (String field : List.of("content", "parts")) {
        JsonNode container = owner.path(field);
        if (container.isArray()) {
          for (JsonNode block : container) {
            if (block.isObject()) blocks.add(block);
          }
        } else if (container.isObject()) {
          blocks.add(container);
        }
      }
    }
    return List.copyOf(blocks);
  }

  private static String resultText(JsonNode block) {
    List<String> parts = new ArrayList<>();
    for (String field : List.of("text", "parts", "content")) {
      JsonNode value = block.path(field);
      if (!value.isMissingNode() && !value.isNull()) parts.add(text(value));
    }
    return String.join("\n", parts);
  }

  private static void declaration(
      Map<String, SourceUnitCatalogEntry> catalog,
      String key,
      String path,
      int order,
      JsonNode source)
      throws IOException {
    String id =
        "tool_use".equals(source.path("type").asText())
            ? source.path("id").asText()
            : source.path("call_id").asText(source.path("id").asText());
    if (id.isBlank()) {
      return;
    }
    JsonNode input = source.has("arguments") ? source.path("arguments") : source.path("input");
    String arguments =
        input.isMissingNode() || input.isNull()
            ? ""
            : input.isTextual() ? input.asText() : input.toString();
    Map<String, Object> unit =
        Map.of(
            "type",
            "tool_use",
            "role",
            "assistant",
            "id",
            id,
            "name",
            source.path("name").asText(),
            "input",
            arguments);
    put(catalog, entry(key, path, "tool_use", order, id, "", unit));
  }

  private static String text(JsonNode content) {
    if (content.isMissingNode() || content.isNull()) {
      return "";
    }
    if (content.isTextual()) {
      return content.asText();
    }
    if (content.isArray()) {
      var text = new StringBuilder();
      for (JsonNode part : content) {
        if (!text.isEmpty()) {
          text.append('\n');
        }
        text.append(text(part));
      }
      return text.toString();
    }
    if (content.isObject()
        && (content.has("text") || content.has("parts") || content.has("content"))) {
      return resultText(content);
    }
    return content.toString();
  }

  private static SourceUnitCatalogEntry entry(
      String key, String path, String type, int order, String label, String text, Object payload) {
    return new SourceUnitCatalogEntry(
        key,
        path,
        key,
        type,
        "",
        "tool_use".equals(type) ? SourceUnitDirection.RESPONSE : SourceUnitDirection.REQUEST,
        order,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.of(label),
        50,
        Optional.empty(),
        Optional.of(text),
        payload,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  private static void put(Map<String, SourceUnitCatalogEntry> catalog, SourceUnitCatalogEntry entry)
      throws IOException {
    if (catalog.size() >= NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw ImportInputValidator.failure("analysis_too_large");
    }
    catalog.put(entry.unitKey(), entry);
  }
}
