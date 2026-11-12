package com.feipi.session.browser.scan.engine.imports;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
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
import java.util.Set;

/** 保存完整原始事件与独立工具结果；不改变共享归一化的计量或调用归属。 */
final class ImportPayloadCatalog {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Set<String> TOOL_TYPES =
      Set.of(
          "tool_use",
          "tool_result",
          "function_call",
          "custom_tool_call",
          "function_call_output",
          "custom_tool_call_output");

  private ImportPayloadCatalog() {}

  /** 将无调用输入附着到原事件身份，保留原始记录但不为每条输入复制一个目录槽位。 */
  static void mergeObserved(
      Map<String, SourceUnitCatalogEntry> catalog,
      Map<String, SourceUnitCatalogEntry> normalized,
      String logicalPath)
      throws IOException {
    for (var value : normalized.values()) {
      if (!"observed_user_message".equals(value.candidate())) continue;
      var raw = catalog.remove(logicalPath + "#raw[" + value.eventOrder() + "]");
      var entry =
          new SourceUnitCatalogEntry(
              value.unitKey(),
              value.originPath(),
              value.canonicalSourceLocator(),
              value.unitType(),
              value.candidate(),
              value.direction(),
              value.eventOrder(),
              value.partIndex(),
              value.byteRange(),
              value.contentHash(),
              value.timestamp(),
              value.label(),
              value.priority(),
              value.preview(),
              value.text(),
              raw == null ? value.payload() : raw.payload(),
              value.subSource(),
              value.sourceCandidate(),
              value.diagnostics());
      put(catalog, entry);
    }
  }

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
        String key = logicalPath + "#raw[" + index + "]";
        put(catalog, entry(key, logicalPath, "import_raw_event", index, "", "", line));
        if (!containsToolType(line)) {
          index++;
          continue;
        }
        JsonNode event = MAPPER.readTree(line);
        int part = 0;
        boolean hasNestedResult = false;
        for (JsonNode block : contentBlocks(event)) {
          if ("tool_result".equals(block.path("type").asText())) {
            hasNestedResult = true;
            String id =
                block
                    .path("tool_use_id")
                    .asText(block.path("call_id").asText(block.path("id").asText()));
            result(catalog, key + "/result/" + part, logicalPath, index, id, block);
          } else if ("tool_use".equals(block.path("type").asText())) {
            declaration(catalog, key + "/tool/" + part, logicalPath, index, block);
          }
          part++;
        }
        if (!hasNestedResult && "tool_result".equals(event.path("type").asText())) {
          String id = event.path("tool_use_id").asText(event.path("call_id").asText());
          result(catalog, key + "/result", logicalPath, index, id, event);
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

  /** 先用 token 流筛掉没有工具结构的行，避免为普通长消息创建完整 JsonNode 树。 */
  private static boolean containsToolType(String line) throws IOException {
    try (JsonParser parser = MAPPER.getFactory().createParser(line)) {
      JsonToken token;
      while ((token = parser.nextToken()) != null) {
        if (token == JsonToken.FIELD_NAME && "type".equals(parser.currentName())) {
          token = parser.nextToken();
          if (token == JsonToken.VALUE_STRING && TOOL_TYPES.contains(parser.getText())) return true;
        }
      }
    }
    return false;
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

  private static void result(
      Map<String, SourceUnitCatalogEntry> catalog,
      String key,
      String path,
      int order,
      String id,
      JsonNode source)
      throws IOException {
    put(catalog, entry(key, path, "tool_result", order, id, resultText(source), source.toString()));
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
    if (catalog.size() >= NormalizedConstants.MAX_SOURCE_UNIT_CATALOG_SIZE) {
      throw ImportInputValidator.failure("analysis_too_large");
    }
    catalog.put(entry.unitKey(), entry);
  }
}
