package com.feipi.session.browser.normalization;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 调用构建器。
 *
 * <p>从原始事件列表和分类后的事件构建 {@link NormalizedCall} 和 {@link NormalizedToolExecution} 列表。 每个助手 消息对应一个
 * {@code NormalizedCall}，工具调用通过 {@code tool_use_id} 关联到声明和消费它的调用。
 *
 * <p>构建过程为确定性的：相同的事件输入始终产生相同的调用列表。
 *
 * <p>工具结果匹配规则：按原始事件流顺序遍历，每个 {@code tool_result} 被分配给紧随其后的下一个助手调用。 若后续无助手 调用，则归因于最后一个调用。
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类内部多个方法（buildCalls、buildToolExecutions、extractCallId 等）
 * 存在结构性相似（语句级 STATEMENT_DUPLICATE），原因：均为 builder 模式中的字段提取和条件组装逻辑， 各方法处理不同的 JsonNode 字段但遵循相同的
 * null-safe 提取模式。此重复是 builder 模式的固有特征。
 */
public final class CallBuilder {

  /** 防止实例化。 */
  private CallBuilder() {}

  /**
   * 从原始事件列表和分类事件构建归一化调用列表。
   *
   * @param events 原始事件列表（保持事件流顺序），用于确定 tool_result 归属
   * @param classified 分类后的事件
   * @return 不可变的 {@link NormalizedCall} 列表，按遍历顺序排列
   */
  public static List<NormalizedCall> buildCalls(
      List<JsonNode> events, EventClassifier.ClassifiedEvents classified) {
    List<JsonNode> assistantMessages = classified.assistantMessages();
    if (assistantMessages.isEmpty()) {
      return List.of();
    }

    // 构建助手调用 ID 列表，用于 tool_result 匹配
    List<String> assistantCallIds = new ArrayList<>();
    for (int i = 0; i < assistantMessages.size(); i++) {
      assistantCallIds.add(extractCallId(assistantMessages.get(i), i + 1));
    }

    // 遍历原始事件流，建立 toolResultId → 消费它的 callId 映射
    Map<String, String> toolResultToConsumerCallId =
        buildToolResultToConsumerMap(events, assistantCallIds);

    List<NormalizedCall> calls = new ArrayList<>();
    for (int i = 0; i < assistantMessages.size(); i++) {
      JsonNode event = assistantMessages.get(i);
      int callIndex = i + 1;
      String callId = assistantCallIds.get(i);
      String callKey = "C" + callIndex;

      // 提取工具调用
      List<ToolCallInfo> toolCalls = extractToolCalls(event);

      // 查找该调用消费的工具结果
      List<String> toolResultIds = new ArrayList<>();
      for (JsonNode trEvent : classified.toolResults()) {
        String trId = extractToolUseIdField(trEvent);
        if (trId != null && callId.equals(toolResultToConsumerCallId.get(trId))) {
          toolResultIds.add(trId);
        }
      }

      // 提取 usage
      NormalizedCallUsage usage = TokenAccountant.extractUsage(event);

      // 构建 NormalizedCall
      NormalizedCall call =
          new NormalizedCall(
              callId,
              callIndex,
              callKey,
              NormalizationConstants.SCOPE_MAIN,
              Optional.empty(),
              Optional.empty(),
              extractTurnId(event),
              extractModel(event),
              extractTimestamp(event),
              usage,
              new NormalizedCallRequest(toolResultIds),
              new NormalizedCallResponse(toolCalls.stream().map(tc -> tc.toolCallId).toList()),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());
      calls.add(call);
    }

    return List.copyOf(calls);
  }

  /**
   * 从原始事件列表和分类事件构建工具执行边列表。
   *
   * @param events 原始事件列表（保持事件流顺序），用于确定 tool_result 归属
   * @param classified 分类后的事件
   * @param calls 已构建的调用列表
   * @return 不可变的 {@link NormalizedToolExecution} 列表
   */
  public static List<NormalizedToolExecution> buildToolExecutions(
      List<JsonNode> events,
      EventClassifier.ClassifiedEvents classified,
      List<NormalizedCall> calls) {

    List<JsonNode> assistantMessages = classified.assistantMessages();

    // 构建助手调用 ID 列表
    List<String> assistantCallIds = new ArrayList<>();
    for (int i = 0; i < assistantMessages.size(); i++) {
      assistantCallIds.add(extractCallId(assistantMessages.get(i), i + 1));
    }

    // 遍历原始事件流，建立 toolResultId → 消费它的 callId 映射
    Map<String, String> toolResultToConsumerCallId =
        buildToolResultToConsumerMap(events, assistantCallIds);

    List<NormalizedToolExecution> executions = new ArrayList<>();

    // 处理助手消息中的工具调用
    for (int i = 0; i < assistantMessages.size(); i++) {
      JsonNode event = assistantMessages.get(i);
      String callId = assistantCallIds.get(i);
      List<ToolCallInfo> toolCalls = extractToolCalls(event);
      for (ToolCallInfo info : toolCalls) {
        String consumerCallId = toolResultToConsumerCallId.get(info.toolCallId());
        NormalizedToolExecution exec =
            new NormalizedToolExecution(
                info.toolCallId(),
                info.name(),
                NormalizationConstants.SCOPE_MAIN,
                callId,
                Optional.ofNullable(consumerCallId),
                Optional.empty(),
                Optional.empty(),
                0L,
                List.of(),
                Optional.empty());
        executions.add(exec);
      }
    }

    // 处理独立 tool_use 事件
    for (JsonNode toolUseEvent : classified.toolUses()) {
      String toolCallId = getTextOrNull(toolUseEvent, "id");
      String name = getTextOrNull(toolUseEvent, "name");
      if (toolCallId == null || name == null) {
        continue;
      }
      // 独立工具调用归属于最后一个助手调用
      String declaredByCallId = calls.isEmpty() ? "unknown" : calls.get(calls.size() - 1).callId();

      String consumerCallId = toolResultToConsumerCallId.get(toolCallId);

      NormalizedToolExecution exec =
          new NormalizedToolExecution(
              toolCallId,
              name,
              NormalizationConstants.SCOPE_MAIN,
              declaredByCallId,
              Optional.ofNullable(consumerCallId),
              Optional.empty(),
              Optional.empty(),
              0L,
              List.of(),
              Optional.empty());
      executions.add(exec);
    }

    return List.copyOf(executions);
  }

  /**
   * 遍历原始事件流，建立 {@code toolResultId} 到消费它的 {@code callId} 的映射。
   *
   * <p>规则：按事件流顺序，每个 {@code tool_result} 被分配给紧随其后的下一个助手调用。 若后续无助手调用，则归因于最后一个助手调用。
   *
   * @param events 原始事件列表
   * @param assistantCallIds 按顺序排列的助手调用 ID 列表
   * @return toolResultId → consumerCallId 映射
   */
  private static Map<String, String> buildToolResultToConsumerMap(
      List<JsonNode> events, List<String> assistantCallIds) {
    Map<String, String> map = new LinkedHashMap<>();
    if (assistantCallIds.isEmpty()) {
      return map;
    }

    int nextAssistantIdx = 0;
    String lastCallId = assistantCallIds.get(assistantCallIds.size() - 1);

    for (JsonNode event : events) {
      if (event == null || !event.isObject()) {
        continue;
      }
      JsonNode typeNode = event.get("type");
      if (typeNode == null || !typeNode.isTextual()) {
        continue;
      }
      String type = typeNode.asText();

      if ("assistant".equals(type)) {
        if (nextAssistantIdx < assistantCallIds.size()) {
          nextAssistantIdx++;
        }
      } else if ("tool_result".equals(type)) {
        String toolUseId = extractToolUseIdField(event);
        if (toolUseId != null) {
          if (nextAssistantIdx < assistantCallIds.size()) {
            map.put(toolUseId, assistantCallIds.get(nextAssistantIdx));
          } else {
            map.put(toolUseId, lastCallId);
          }
        }
      }
    }

    return map;
  }

  private static String extractCallId(JsonNode event, int fallbackIndex) {
    JsonNode idNode = event.get("id");
    if (idNode != null && idNode.isTextual()) {
      return idNode.asText();
    }
    JsonNode uuidNode = event.get("uuid");
    if (uuidNode != null && uuidNode.isTextual()) {
      return uuidNode.asText();
    }
    return "C" + fallbackIndex;
  }

  private static String extractModel(JsonNode event) {
    JsonNode modelNode = event.get("model");
    if (modelNode != null && modelNode.isTextual()) {
      return modelNode.asText();
    }
    return "";
  }

  private static Optional<String> extractTimestamp(JsonNode event) {
    JsonNode tsNode = event.get("timestamp");
    if (tsNode != null && tsNode.isTextual()) {
      return Optional.of(tsNode.asText());
    }
    return Optional.empty();
  }

  private static Optional<String> extractTurnId(JsonNode event) {
    JsonNode turnNode = event.get("turn_id");
    if (turnNode != null && turnNode.isTextual()) {
      return Optional.of(turnNode.asText());
    }
    JsonNode turnIdNode = event.get("turnId");
    if (turnIdNode != null && turnIdNode.isTextual()) {
      return Optional.of(turnIdNode.asText());
    }
    return Optional.empty();
  }

  /**
   * 从助手事件的 {@code content} 数组中提取工具调用信息。
   *
   * @param event 助手类型的事件
   * @return 工具调用信息列表
   */
  static List<ToolCallInfo> extractToolCalls(JsonNode event) {
    JsonNode contentNode = event.get("content");
    if (contentNode == null || !contentNode.isArray()) {
      return List.of();
    }
    List<ToolCallInfo> result = new ArrayList<>();
    for (JsonNode block : contentNode) {
      JsonNode typeNode = block.get("type");
      if (typeNode != null && "tool_use".equals(typeNode.asText())) {
        String id = getTextOrNull(block, "id");
        String name = getTextOrNull(block, "name");
        if (id != null && name != null) {
          result.add(new ToolCallInfo(id, name));
        }
      }
    }
    return result;
  }

  private static String extractToolUseIdField(JsonNode event) {
    JsonNode idNode = event.get("tool_use_id");
    if (idNode != null && idNode.isTextual()) {
      return idNode.asText();
    }
    return null;
  }

  private static String getTextOrNull(JsonNode node, String fieldName) {
    JsonNode child = node.get(fieldName);
    if (child != null && child.isTextual()) {
      return child.asText();
    }
    return null;
  }

  /**
   * 工具调用信息内部载体。
   *
   * @param toolCallId 工具调用标识符
   * @param name 工具名称
   */
  record ToolCallInfo(String toolCallId, String name) {}
}
