package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import com.feipi.session.browser.source.common.JsonNodeReaders;
import com.feipi.session.browser.source.common.ToolFailureClassifier;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalLong;

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
   * 将 JSON 事件映射为源中性记录列表。
   *
   * <p>含 tool_result 的 user 事件按块保持顺序，文本仍归属 user，工具结果独立归属且用量只记录一次。其他事件返回单元素列表。
   *
   * @param locator 源记录定位符
   * @param eventIndex 事件在源输入中的序号
   * @param event JSON 事件对象
   * @param eventType 已由 adapter 判定的源中性事件类型
   * @return 源中性记录列表
   */
  public static List<SourceRecord> toSourceRecords(
      String locator, int eventIndex, JsonNode event, String eventType) {
    String recordLocator = locator + "#event[" + eventIndex + "]";
    String normalizedEventType = normalizeEventType(event, eventType);

    if (("user".equals(eventType) || "tool_result".equals(eventType))
        && hasToolResultBlock(event)) {
      List<JsonNode> blocks = new ArrayList<>();
      for (JsonNode container : contentContainers(event)) {
        if (container.isArray()) {
          container.forEach(blocks::add);
        } else {
          blocks.add(container);
        }
      }
      List<SourceRecord> records = new ArrayList<>();
      for (int i = 0; i < blocks.size(); i++) {
        JsonNode block = blocks.get(i);
        String blockLocator = blocks.size() == 1 ? recordLocator : recordLocator + "[" + i + "]";
        SourceRecordUsage usage = i == 0 ? extractUsage(event) : SourceRecordUsage.empty();
        records.add(createBlockRecord(blockLocator, eventIndex, event, block, usage));
      }
      return List.copyOf(records);
    }
    return List.of(createSingleRecord(recordLocator, eventIndex, event, normalizedEventType));
  }

  private static SourceRecord createSingleRecord(
      String recordLocator, int eventIndex, JsonNode event, String normalizedEventType) {
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
        extractToolError(event, normalizedEventType),
        com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
        extractContent(event),
        extractResponseMessageId(event, normalizedEventType),
        extractResponseStopReason(event, normalizedEventType),
        extractTiming(event),
        isMetaContext(event),
        messageRole(event, normalizedEventType));
  }

  private static SourceRecord createBlockRecord(
      String blockLocator,
      int eventIndex,
      JsonNode event,
      JsonNode block,
      SourceRecordUsage usage) {
    boolean toolResult = "tool_result".equals(block.path("type").asText());
    String eventType = toolResult ? "tool_result" : "user";
    StringBuilder content = new StringBuilder();
    appendTextValue(content, block, false);
    Optional<String> toolName =
        toolResult
            ? firstText(block, "name").or(() -> firstTextDeep(event, "name"))
            : Optional.empty();
    Optional<String> toolError = Optional.empty();
    if (toolResult) {
      if (block.path("is_error").asBoolean(false) || event.path("is_error").asBoolean(false)) {
        toolError = Optional.of("tool_error");
      } else if (ToolFailureClassifier.looksFailed(content.toString(), toolName.orElse(""))) {
        toolError = Optional.of("text_heuristic_failure");
      }
    }
    return new SourceRecord(
        blockLocator,
        eventIndex,
        eventType,
        toolResult ? Optional.empty() : firstTextDeep(event, "id", "uuid", "call_id"),
        firstTextDeep(event, "model"),
        firstTextDeep(event, "timestamp"),
        extractTurnId(event, eventType),
        usage,
        List.of(),
        toolResult ? firstText(block, "tool_use_id", "call_id", "id") : Optional.empty(),
        toolName,
        toolError,
        com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
        content.toString(),
        Optional.empty(),
        Optional.empty(),
        extractTiming(event),
        isMetaContext(event),
        toolResult ? Optional.empty() : messageRole(event, eventType));
  }

  private static Optional<String> messageRole(JsonNode event, String type) {
    String rawType = event.path("type").asText("");
    String role = event.path("role").asText(event.path("message").path("role").asText(""));
    if (("user".equals(type) || "assistant".equals(type))
        && (type.equals(rawType) || type.equals(role))) {
      return Optional.of(type);
    }
    return Optional.empty();
  }

  private static boolean isMetaContext(JsonNode event) {
    JsonNode value = event.get("isMeta");
    return value != null && value.isBoolean() && value.booleanValue();
  }

  /** 只提取显式任务/agent-turn计时；外层timestamp是写出时间，不能代替任务边界。 */
  public static SourceTiming extractTiming(JsonNode event) {
    String type = event.path("type").asText("");
    JsonNode fields = "event_msg".equals(type) ? event.path("payload") : event;
    String kind = "event_msg".equals(type) ? fields.path("type").asText("") : type;
    if ("system".equals(type) && "turn_duration".equals(event.path("subtype").asText())) {
      kind = "turn_duration";
    }
    if (!List.of("task_started", "task_complete", "turn_aborted", "turn_duration").contains(kind)) {
      return SourceTiming.empty();
    }
    return new SourceTiming(
        kind,
        fields.path("turn_id").asText(""),
        explicitTime(fields.get("started_at")),
        explicitTime(fields.get("completed_at")),
        explicitMillis(fields.get("turn_duration".equals(kind) ? "durationMs" : "duration_ms")),
        OptionalLong.empty(),
        OptionalLong.empty(),
        firstText(event, "uuid", "id").orElse(""));
  }

  private static Optional<String> explicitTime(JsonNode value) {
    if (value == null || value.isNull()) {
      return Optional.empty();
    }
    try {
      if (value.isIntegralNumber() && value.canConvertToLong()) {
        return Optional.of(Instant.ofEpochSecond(value.longValue()).toString());
      }
      if (value.isTextual()) {
        return Optional.of(Instant.parse(value.textValue()).toString());
      }
    } catch (java.time.DateTimeException e) {
      return Optional.empty();
    }
    return Optional.empty();
  }

  private static OptionalLong explicitMillis(JsonNode value) {
    return value != null
            && value.isIntegralNumber()
            && value.canConvertToLong()
            && value.longValue() >= 0
        ? OptionalLong.of(value.longValue())
        : OptionalLong.empty();
  }

  private static String normalizeEventType(JsonNode event, String eventType) {
    if ("user".equals(eventType) && hasToolResultBlock(event) && !hasUserText(event)) {
      return "tool_result";
    }
    return eventType;
  }

  private static Optional<String> extractTurnId(JsonNode event, String eventType) {
    if ("assistant".equals(eventType)) {
      JsonNode message = JsonNodeReaders.objectChild(event, "message");
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

  /**
   * 提取 assistant 响应的显式 message.id。
   *
   * <p>仅从 message.id 提取，不使用 uuid/parentUuid 回退。非 assistant 事件返回空。
   *
   * @param event JSON 事件节点
   * @param eventType 事件类型
   * @return 显式 message.id，缺失时为空
   */
  private static Optional<String> extractResponseMessageId(JsonNode event, String eventType) {
    if (!"assistant".equals(eventType)) {
      return Optional.empty();
    }
    JsonNode message = JsonNodeReaders.objectChild(event, "message");
    return firstText(message, "id");
  }

  /**
   * 提取 assistant 响应的 stop_reason。
   *
   * <p>优先从 message.stop_reason 提取，回退到事件顶层 stop_reason（如 end_turn、tool_use）。非 assistant 事件返回空。
   *
   * @param event JSON 事件节点
   * @param eventType 事件类型
   * @return stop_reason，缺失时为空
   */
  private static Optional<String> extractResponseStopReason(JsonNode event, String eventType) {
    if (!"assistant".equals(eventType)) {
      return Optional.empty();
    }
    JsonNode message = JsonNodeReaders.objectChild(event, "message");
    Optional<String> messageStopReason = firstText(message, "stop_reason");
    if (messageStopReason.isPresent()) {
      return messageStopReason;
    }
    return firstText(event, "stop_reason");
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
    JsonNode message = JsonNodeReaders.objectChild(event, "message");
    Optional<String> messageText = firstText(message, fieldNames);
    if (messageText.isPresent()) {
      return messageText;
    }
    JsonNode payload = JsonNodeReaders.objectChild(event, "payload");
    Optional<String> payloadText = firstText(payload, fieldNames);
    if (payloadText.isPresent()) {
      return payloadText;
    }
    JsonNode metadata = JsonNodeReaders.objectChild(event, "metadata");
    Optional<String> metadataText = firstText(metadata, fieldNames);
    if (metadataText.isPresent()) {
      return metadataText;
    }
    JsonNode settings =
        JsonNodeReaders.objectChild(
            JsonNodeReaders.objectChild(payload, "collaboration_mode"), "settings");
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
    boolean inclusiveInput =
        usage.has("cached_input_tokens") && !usage.has("cache_read_input_tokens");
    long freshInput = inclusiveInput ? Math.max(0L, inputTokens - cacheRead) : inputTokens;
    return new SourceRecordUsage(
        freshInput,
        cacheRead,
        readLong(usage, "cache_creation_input_tokens", "cacheCreationInputTokens"),
        readLong(usage, "output_tokens", "outputTokens"),
        Map.of(
            "freshInputTokenPrecision",
                inclusiveInput
                        && "unavailable"
                            .equals(
                                usagePrecision(
                                    usage,
                                    "cache_read_input_tokens",
                                    "cacheReadInputTokens",
                                    "cached_input_tokens"))
                    ? "unavailable"
                    : usagePrecision(usage, "input_tokens", "inputTokens"),
            "cacheReadTokenPrecision",
                usagePrecision(
                    usage,
                    "cache_read_input_tokens",
                    "cacheReadInputTokens",
                    "cached_input_tokens"),
            "cacheWriteTokenPrecision",
                usagePrecision(usage, "cache_creation_input_tokens", "cacheCreationInputTokens"),
            "outputTokenPrecision", usagePrecision(usage, "output_tokens", "outputTokens")));
  }

  private static String usagePrecision(JsonNode usage, String... fields) {
    for (String field : fields) {
      if (usage.path(field).isNumber()) {
        return "provider_reported";
      }
    }
    return "unavailable";
  }

  private static JsonNode usageNode(JsonNode event) {
    JsonNode usage = JsonNodeReaders.objectChild(event, "usage");
    if (usage != null) {
      return usage;
    }
    JsonNode messageUsage =
        JsonNodeReaders.objectChild(JsonNodeReaders.objectChild(event, "message"), "usage");
    if (messageUsage != null) {
      return messageUsage;
    }
    JsonNode payload = JsonNodeReaders.objectChild(event, "payload");
    JsonNode payloadUsage = JsonNodeReaders.objectChild(payload, "usage");
    if (payloadUsage != null) {
      return payloadUsage;
    }
    JsonNode infoUsage =
        JsonNodeReaders.objectChild(
            JsonNodeReaders.objectChild(payload, "info"), "total_token_usage");
    if (infoUsage != null) {
      return infoUsage;
    }
    return JsonNodeReaders.objectChild(payload, "total_token_usage");
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
          String input = serializeToolInput(block);
          calls.add(new SourceToolCall(id.get(), name.get(), input));
        }
      }
    }
  }

  /**
   * 将 tool_use block 的 input 字段序列化为紧凑 JSON 文本。
   *
   * <p>缺失或 null 时返回空字符串；空对象 {@code {}} 返回 {@code "{}"}，与缺失有区别。
   *
   * @param toolUseBlock tool_use 内容块
   * @return input 的 JSON 序列化文本
   */
  private static String serializeToolInput(JsonNode toolUseBlock) {
    JsonNode inputNode = toolUseBlock.get("input");
    if (inputNode == null || inputNode.isNull()) {
      return "";
    }
    return inputNode.toString();
  }

  private static boolean hasUserText(JsonNode event) {
    if (event == null || !event.isObject()) {
      return false;
    }
    JsonNode message = JsonNodeReaders.objectChild(event, "message");
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
    JsonNode message = JsonNodeReaders.objectChild(event, "message");
    if (message != null) {
      addContainer(containers, message.get("content"));
      addContainer(containers, message.get("parts"));
    }
    JsonNode payload = JsonNodeReaders.objectChild(event, "payload");
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

  /**
   * 从事件提取实际文本内容，用于归一化时填充 sourceUnits。
   *
   * @param event JSON 事件节点
   * @return 提取的文本内容，无内容时返回空串
   */
  private static String extractContent(JsonNode event) {
    if (event == null) {
      return "";
    }
    StringBuilder sb = new StringBuilder();
    for (JsonNode container : contentContainers(event)) {
      appendTextValue(sb, container, false);
    }
    return sb.toString();
  }

  private static void appendTextValue(StringBuilder sb, JsonNode value) {
    appendTextValue(sb, value, true);
  }

  private static void appendTextValue(StringBuilder sb, JsonNode value, boolean separateLines) {
    if (value == null) {
      return;
    }
    if (value.isTextual()) {
      appendText(sb, value.asText(), separateLines);
      return;
    }
    if (value.isArray()) {
      for (JsonNode item : value) {
        appendTextValue(sb, item, separateLines);
      }
      return;
    }
    if (value.isObject()) {
      JsonNode text = value.get("text");
      if (text != null && text.isTextual()) {
        appendText(sb, text.asText(), separateLines);
      }
      appendTextValue(sb, value.get("parts"), separateLines);
      JsonNode content = value.get("content");
      if (content != null) {
        appendTextValue(sb, content, separateLines);
      }
    }
  }

  private static void appendText(StringBuilder sb, String text, boolean separateLines) {
    if (text == null || (separateLines && text.isBlank())) {
      return;
    }
    if (separateLines && !sb.isEmpty()) {
      sb.append("\n");
    }
    sb.append(text);
  }
}
