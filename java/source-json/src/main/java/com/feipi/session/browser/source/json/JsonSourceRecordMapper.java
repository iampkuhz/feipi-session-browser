package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * JSON 事件到源中性记录的映射器。
 *
 * <p>该工具只从 provider JSON 中提取归一化所需的稳定字段，输出 core-domain {@link SourceRecord}；不会把 {@link JsonNode} 暴露到
 * source SPI 或 normalization engine。
 */
public final class JsonSourceRecordMapper {

  /** 防止实例化。 */
  private JsonSourceRecordMapper() {}

  /**
   * 将 JSON 事件映射为源中性记录。
   *
   * @param locator 源记录定位符
   * @param eventIndex 事件在源输入中的序号
   * @param event JSON 事件对象
   * @param eventType 已由 adapter 判定的源中性事件类型
   * @return 源中性记录
   */
  public static SourceRecord toSourceRecord(
      String locator, int eventIndex, JsonNode event, String eventType) {
    String recordLocator = locator + "#event[" + eventIndex + "]";
    String normalizedEventType = normalizeEventType(event, eventType);
    return new SourceRecord(
        recordLocator,
        eventIndex,
        normalizedEventType,
        firstTextDeep(event, "id", "uuid", "call_id"),
        firstTextDeep(event, "model"),
        firstTextDeep(event, "timestamp"),
        extractTurnId(event, normalizedEventType),
        extractUsage(event),
        extractToolCalls(event),
        extractToolUseId(event, normalizedEventType),
        extractToolName(event),
        extractToolError(event, normalizedEventType));
  }

  private static String normalizeEventType(JsonNode event, String eventType) {
    if ("user".equals(eventType) && hasToolResultBlock(event) && !hasUserText(event)) {
      return "tool_result";
    }
    return eventType;
  }

  private static Optional<String> extractTurnId(JsonNode event, String eventType) {
    if ("assistant".equals(eventType)) {
      JsonNode message = objectChild(event, "message");
      Optional<String> messageId = firstText(message, "id");
      if (messageId.isPresent()) {
        return messageId;
      }
      Optional<String> semanticId = firstText(event, "uuid", "parentUuid", "id");
      if (semanticId.isPresent()) {
        return semanticId;
      }
    }
    return firstTextDeep(event, "turn_id", "turnId");
  }

  private static Optional<String> extractToolUseId(JsonNode event, String eventType) {
    if ("tool_result".equals(eventType)) {
      Optional<String> nested = firstToolResultText(event, "tool_use_id", "call_id", "id");
      if (nested.isPresent()) {
        return nested;
      }
    }
    return firstTextDeep(event, "tool_use_id", "call_id");
  }

  private static Optional<String> extractToolName(JsonNode event) {
    Optional<String> direct = firstTextDeep(event, "name");
    if (direct.isPresent()) {
      return direct;
    }
    return firstToolUseText(event, "name");
  }

  private static Optional<String> firstTextDeep(JsonNode event, String... fieldNames) {
    Optional<String> direct = firstText(event, fieldNames);
    if (direct.isPresent()) {
      return direct;
    }
    JsonNode message = objectChild(event, "message");
    Optional<String> messageText = firstText(message, fieldNames);
    if (messageText.isPresent()) {
      return messageText;
    }
    JsonNode payload = objectChild(event, "payload");
    Optional<String> payloadText = firstText(payload, fieldNames);
    if (payloadText.isPresent()) {
      return payloadText;
    }
    JsonNode metadata = objectChild(event, "metadata");
    Optional<String> metadataText = firstText(metadata, fieldNames);
    if (metadataText.isPresent()) {
      return metadataText;
    }
    JsonNode settings = objectChild(objectChild(payload, "collaboration_mode"), "settings");
    return firstText(settings, fieldNames);
  }

  private static Optional<String> firstText(JsonNode event, String... fieldNames) {
    if (event == null) {
      return Optional.empty();
    }
    for (String fieldName : fieldNames) {
      JsonNode child = event.get(fieldName);
      if (child != null && child.isTextual()) {
        return Optional.of(child.asText());
      }
    }
    return Optional.empty();
  }

  private static Optional<String> firstToolResultText(JsonNode event, String... fieldNames) {
    for (JsonNode block : toolResultBlocks(event)) {
      Optional<String> value = firstText(block, fieldNames);
      if (value.isPresent()) {
        return value;
      }
    }
    return Optional.empty();
  }

  private static Optional<String> firstToolUseText(JsonNode event, String... fieldNames) {
    for (JsonNode container : contentContainers(event)) {
      if (container != null && container.isArray()) {
        for (JsonNode block : container) {
          if (block != null
              && block.isObject()
              && block.has("type")
              && "tool_use".equals(block.get("type").asText())) {
            Optional<String> value = firstText(block, fieldNames);
            if (value.isPresent()) {
              return value;
            }
          }
        }
      }
    }
    return Optional.empty();
  }

  private static SourceRecordUsage extractUsage(JsonNode event) {
    if (event == null) {
      return SourceRecordUsage.empty();
    }
    JsonNode usage = usageNode(event);
    if (usage == null || !usage.isObject()) {
      return SourceRecordUsage.empty();
    }
    long inputTokens = readLong(usage, "input_tokens", "inputTokens");
    long cacheRead =
        readLong(usage, "cache_read_input_tokens", "cacheReadInputTokens", "cached_input_tokens");
    long freshInput =
        usage.has("cached_input_tokens") && !usage.has("cache_read_input_tokens")
            ? Math.max(0L, inputTokens - cacheRead)
            : inputTokens;
    return new SourceRecordUsage(
        freshInput,
        cacheRead,
        readLong(usage, "cache_creation_input_tokens", "cacheCreationInputTokens"),
        readLong(usage, "output_tokens", "outputTokens"));
  }

  private static JsonNode usageNode(JsonNode event) {
    JsonNode usage = objectChild(event, "usage");
    if (usage != null) {
      return usage;
    }
    JsonNode messageUsage = objectChild(objectChild(event, "message"), "usage");
    if (messageUsage != null) {
      return messageUsage;
    }
    JsonNode payload = objectChild(event, "payload");
    JsonNode payloadUsage = objectChild(payload, "usage");
    if (payloadUsage != null) {
      return payloadUsage;
    }
    JsonNode infoUsage = objectChild(objectChild(payload, "info"), "total_token_usage");
    if (infoUsage != null) {
      return infoUsage;
    }
    return objectChild(payload, "total_token_usage");
  }

  private static JsonNode objectChild(JsonNode node, String fieldName) {
    if (node == null || !node.isObject()) {
      return null;
    }
    JsonNode child = node.get(fieldName);
    return child != null && child.isObject() ? child : null;
  }

  private static long readLong(JsonNode node, String... fieldNames) {
    for (String fieldName : fieldNames) {
      JsonNode child = node.get(fieldName);
      if (child != null && child.isNumber()) {
        return child.asLong();
      }
    }
    return 0L;
  }

  private static List<SourceToolCall> extractToolCalls(JsonNode event) {
    if (event == null) {
      return List.of();
    }
    List<SourceToolCall> calls = new ArrayList<>();
    for (JsonNode container : contentContainers(event)) {
      collectToolCalls(container, calls);
    }
    return List.copyOf(calls);
  }

  private static void collectToolCalls(JsonNode blocks, List<SourceToolCall> calls) {
    if (blocks == null || !blocks.isArray()) {
      return;
    }
    for (JsonNode block : blocks) {
      JsonNode typeNode = block.get("type");
      if (typeNode != null && "tool_use".equals(typeNode.asText())) {
        Optional<String> id = firstText(block, "id");
        Optional<String> name = firstText(block, "name");
        if (id.isPresent() && name.isPresent()) {
          calls.add(new SourceToolCall(id.get(), name.get()));
        }
      }
    }
  }

  private static boolean hasUserText(JsonNode event) {
    if (event == null || !event.isObject()) {
      return false;
    }
    JsonNode message = objectChild(event, "message");
    if (hasTextBlock(message == null ? null : message.get("content"))) {
      return true;
    }
    if (hasTextBlock(message == null ? null : message.get("parts"))) {
      return true;
    }
    if (hasTextBlock(event.get("content"))) {
      return true;
    }
    return hasTextBlock(event.get("parts"));
  }

  private static boolean hasTextBlock(JsonNode value) {
    if (value == null) {
      return false;
    }
    if (value.isTextual()) {
      return !value.asText().isBlank();
    }
    if (!value.isArray()) {
      return false;
    }
    for (JsonNode item : value) {
      if (item == null) {
        continue;
      }
      if (item.isTextual() && !item.asText().isBlank()) {
        return true;
      }
      if (item.isObject()
          && item.has("type")
          && "text".equals(item.get("type").asText())
          && item.has("text")
          && item.get("text").isTextual()
          && !item.get("text").asText().isBlank()) {
        return true;
      }
    }
    return false;
  }

  private static boolean hasToolResultBlock(JsonNode event) {
    return !toolResultBlocks(event).isEmpty();
  }

  private static List<JsonNode> toolResultBlocks(JsonNode event) {
    if (event == null) {
      return List.of();
    }
    List<JsonNode> blocks = new ArrayList<>();
    for (JsonNode container : contentContainers(event)) {
      if (container == null) {
        continue;
      }
      if (container.isObject()
          && container.has("type")
          && "tool_result".equals(container.get("type").asText())) {
        blocks.add(container);
      } else if (container.isArray()) {
        for (JsonNode block : container) {
          if (block != null
              && block.isObject()
              && block.has("type")
              && "tool_result".equals(block.get("type").asText())) {
            blocks.add(block);
          }
        }
      }
    }
    return List.copyOf(blocks);
  }

  private static List<JsonNode> contentContainers(JsonNode event) {
    if (event == null) {
      return List.of();
    }
    List<JsonNode> containers = new ArrayList<>();
    addContainer(containers, event.get("content"));
    addContainer(containers, event.get("parts"));
    JsonNode message = objectChild(event, "message");
    if (message != null) {
      addContainer(containers, message.get("content"));
      addContainer(containers, message.get("parts"));
    }
    JsonNode payload = objectChild(event, "payload");
    if (payload != null) {
      addContainer(containers, payload.get("content"));
      addContainer(containers, payload.get("parts"));
    }
    return List.copyOf(containers);
  }

  private static void addContainer(List<JsonNode> containers, JsonNode node) {
    if (node != null && !node.isNull()) {
      containers.add(node);
    }
  }

  /**
   * 从工具结果事件提取错误信息。
   *
   * <p>检测 content blocks 中的 {@code is_error: true} 或顶层 {@code is_error} 字段。 若 {@code is_error}
   * 未命中，则通过 {@link ToolFailureClassifier} 进行文本启发式失败检测。
   *
   * @param event JSON 事件节点
   * @param eventType 已判定的事件类型
   * @return 错误信息，非空表示工具执行失败
   */
  private static Optional<String> extractToolError(JsonNode event, String eventType) {
    if (!"tool_result".equals(eventType) || event == null) {
      return Optional.empty();
    }
    JsonNode isError = event.get("is_error");
    if (isError != null && isError.isBoolean() && isError.asBoolean()) {
      return Optional.of("tool_error");
    }
    String toolName = "";
    for (JsonNode block : toolResultBlocks(event)) {
      JsonNode blockError = block.get("is_error");
      if (blockError != null && blockError.isBoolean() && blockError.asBoolean()) {
        return Optional.of("tool_error");
      }
    }
    for (JsonNode container : contentContainers(event)) {
      if (container != null && container.isArray()) {
        for (JsonNode block : container) {
          if (block != null
              && block.isObject()
              && block.has("type")
              && "tool_use".equals(block.get("type").asText())) {
            Optional<String> name = firstText(block, "name");
            if (name.isPresent()) {
              toolName = name.get();
            }
          }
        }
      }
    }

    if (toolName.isEmpty()) {
      toolName = firstTextDeep(event, "name").orElse("");
    }
    String contentString = toolResultContentString(event);
    if (!contentString.isEmpty() && ToolFailureClassifier.looksFailed(contentString, toolName)) {
      return Optional.of("text_heuristic_failure");
    }

    return Optional.empty();
  }

  /**
   * 从工具结果事件提取内容文本，用于文本启发式失败检测。
   *
   * @param event 工具结果事件 JSON 节点
   * @return 内容文本，不含内容时返回空串
   */
  static String toolResultContentString(JsonNode event) {
    StringBuilder sb = new StringBuilder();
    for (JsonNode block : toolResultBlocks(event)) {
      appendTextValue(sb, block.get("content"));
      appendTextValue(sb, block.get("text"));
    }
    for (JsonNode blocks : contentContainers(event)) {
      appendTextValue(sb, blocks);
    }
    return sb.toString();
  }

  private static void appendTextValue(StringBuilder sb, JsonNode value) {
    if (value == null) {
      return;
    }
    if (value.isTextual()) {
      appendLine(sb, value.asText());
      return;
    }
    if (value.isArray()) {
      for (JsonNode item : value) {
        appendTextValue(sb, item);
      }
      return;
    }
    if (value.isObject()) {
      JsonNode text = value.get("text");
      if (text != null && text.isTextual()) {
        appendLine(sb, text.asText());
      }
      JsonNode content = value.get("content");
      if (content != null) {
        appendTextValue(sb, content);
      }
    }
  }

  private static void appendLine(StringBuilder sb, String text) {
    if (text == null || text.isBlank()) {
      return;
    }
    if (!sb.isEmpty()) {
      sb.append("\n");
    }
    sb.append(text);
  }
}
