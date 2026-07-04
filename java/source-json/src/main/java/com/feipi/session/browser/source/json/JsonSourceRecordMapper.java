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
    return new SourceRecord(
        recordLocator,
        eventIndex,
        eventType,
        firstTextDeep(event, "id", "uuid", "call_id"),
        firstTextDeep(event, "model"),
        firstTextDeep(event, "timestamp"),
        firstTextDeep(event, "turn_id", "turnId"),
        extractUsage(event),
        extractToolCalls(event),
        firstTextDeep(event, "tool_use_id", "call_id"),
        firstTextDeep(event, "name"),
        extractToolError(event, eventType));
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
    collectToolCalls(event.get("content"), calls);
    collectToolCalls(event.get("parts"), calls);
    JsonNode message = objectChild(event, "message");
    collectToolCalls(message == null ? null : message.get("content"), calls);
    collectToolCalls(message == null ? null : message.get("parts"), calls);
    JsonNode payload = objectChild(event, "payload");
    collectToolCalls(payload == null ? null : payload.get("content"), calls);
    collectToolCalls(payload == null ? null : payload.get("parts"), calls);
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

  /**
   * 从工具结果事件提取错误信息。
   *
   * <p>检测 content blocks 中的 {@code is_error: true} 或顶层 {@code is_error} 字段。
   *
   * @param event JSON 事件节点
   * @param eventType 已判定的事件类型
   * @return 错误信息，非空表示工具执行失败
   */
  private static Optional<String> extractToolError(JsonNode event, String eventType) {
    if (!"tool_result".equals(eventType) || event == null) {
      return Optional.empty();
    }
    // 检查顶层 is_error
    JsonNode isError = event.get("is_error");
    if (isError != null && isError.isBoolean() && isError.asBoolean()) {
      return Optional.of("tool_error");
    }
    // 检查 content blocks 中的 is_error
    for (String container : new String[] {"content", "parts"}) {
      JsonNode blocks = event.get(container);
      if (blocks != null && blocks.isArray()) {
        for (JsonNode block : blocks) {
          JsonNode typeNode = block.get("type");
          if (typeNode != null && "tool_result".equals(typeNode.asText())) {
            JsonNode blockError = block.get("is_error");
            if (blockError != null && blockError.isBoolean() && blockError.asBoolean()) {
              return Optional.of("tool_error");
            }
          }
        }
      }
      // 也检查 message/payload 子节点
      JsonNode message = objectChild(event, "message");
      if (message != null) {
        JsonNode msgBlocks = message.get(container);
        if (msgBlocks != null && msgBlocks.isArray()) {
          for (JsonNode block : msgBlocks) {
            JsonNode typeNode = block.get("type");
            if (typeNode != null && "tool_result".equals(typeNode.asText())) {
              JsonNode blockError = block.get("is_error");
              if (blockError != null && blockError.isBoolean() && blockError.asBoolean()) {
                return Optional.of("tool_error");
              }
            }
          }
        }
      }
    }
    return Optional.empty();
  }
}
