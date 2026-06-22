package com.feipi.session.browser.normalization;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 事件分类器。
 *
 * <p>将原始 JSON 事件列表按 {@code type} 字段分类为归一化引擎可处理的各类别。 分类结果为不可变集合，供 {@link CallBuilder} 和 {@link
 * NormalizationEngine} 使用。
 *
 * <p>识别的事件类型：
 *
 * <ul>
 *   <li>{@code assistant} — 助手消息，每个事件对应一个 {@link
 *       com.feipi.session.browser.domain.normalized.NormalizedCall}
 *   <li>{@code tool_use} — 独立工具调用事件（嵌入在 {@code assistant} 消息中的工具调用由 {@link CallBuilder} 提取）
 *   <li>{@code tool_result} — 工具结果事件
 *   <li>{@code user} — 用户消息事件
 *   <li>其他 — 进入 {@code unknownEvents}，并产生诊断信息
 * </ul>
 */
public final class EventClassifier {

  /** 防止实例化。 */
  private EventClassifier() {}

  /**
   * 将事件列表按类型分类。
   *
   * @param events 原始 JSON 事件列表，不得为 null
   * @return 分类后的事件集合
   */
  public static ClassifiedEvents classify(List<JsonNode> events) {
    if (events == null || events.isEmpty()) {
      return ClassifiedEvents.empty();
    }

    List<JsonNode> assistantMessages = new ArrayList<>();
    List<JsonNode> toolUses = new ArrayList<>();
    List<JsonNode> toolResults = new ArrayList<>();
    List<JsonNode> userMessages = new ArrayList<>();
    List<JsonNode> unknownEvents = new ArrayList<>();

    for (JsonNode event : events) {
      if (event == null) {
        continue;
      }
      if (!event.isObject()) {
        unknownEvents.add(event);
        continue;
      }
      JsonNode typeNode = event.get("type");
      if (typeNode == null || !typeNode.isTextual()) {
        unknownEvents.add(event);
        continue;
      }
      String type = typeNode.asText();
      switch (type) {
        case "assistant" -> assistantMessages.add(event);
        case "tool_use" -> toolUses.add(event);
        case "tool_result" -> toolResults.add(event);
        case "user" -> userMessages.add(event);
        default -> unknownEvents.add(event);
      }
    }

    return new ClassifiedEvents(
        List.copyOf(assistantMessages),
        List.copyOf(toolUses),
        List.copyOf(toolResults),
        List.copyOf(userMessages),
        List.copyOf(unknownEvents));
  }

  /**
   * 分类后的事件集合。
   *
   * <p>不可变数据载体，包含按事件类型分组的列表。
   */
  public static final class ClassifiedEvents {
    private final List<JsonNode> assistantMessages;
    private final List<JsonNode> toolUses;
    private final List<JsonNode> toolResults;
    private final List<JsonNode> userMessages;
    private final List<JsonNode> unknownEvents;

    private static final ClassifiedEvents EMPTY =
        new ClassifiedEvents(List.of(), List.of(), List.of(), List.of(), List.of());

    ClassifiedEvents(
        List<JsonNode> assistantMessages,
        List<JsonNode> toolUses,
        List<JsonNode> toolResults,
        List<JsonNode> userMessages,
        List<JsonNode> unknownEvents) {
      this.assistantMessages = assistantMessages;
      this.toolUses = toolUses;
      this.toolResults = toolResults;
      this.userMessages = userMessages;
      this.unknownEvents = unknownEvents;
    }

    /**
     * 返回空的分类结果。
     *
     * @return 所有类别均为空列表的共享实例
     */
    static ClassifiedEvents empty() {
      return EMPTY;
    }

    /**
     * 获取助手消息事件列表。
     *
     * @return 不可变的助手消息列表
     */
    public List<JsonNode> assistantMessages() {
      return assistantMessages;
    }

    /**
     * 获取独立工具调用事件列表。
     *
     * @return 不可变的工具调用列表
     */
    public List<JsonNode> toolUses() {
      return toolUses;
    }

    /**
     * 获取工具结果事件列表。
     *
     * @return 不可变的工具结果列表
     */
    public List<JsonNode> toolResults() {
      return toolResults;
    }

    /**
     * 获取用户消息事件列表。
     *
     * @return 不可变的消息列表
     */
    public List<JsonNode> userMessages() {
      return userMessages;
    }

    /**
     * 获取未识别类型事件列表。
     *
     * @return 不可变的未知事件列表
     */
    public List<JsonNode> unknownEvents() {
      return unknownEvents;
    }

    /**
     * 获取所有分类事件的总数。
     *
     * @return 各分类事件数量之和
     */
    public int totalCount() {
      return assistantMessages.size()
          + toolUses.size()
          + toolResults.size()
          + userMessages.size()
          + unknownEvents.size();
    }

    /**
     * 是否存在任何事件。
     *
     * @return 当至少一个分类包含事件时返回 {@code true}
     */
    public boolean isEmpty() {
      return totalCount() == 0;
    }

    /**
     * 返回所有分类事件的只读汇总列表，顺序为 {@code assistant}、{@code tool_use}、{@code tool_result}、{@code
     * user}、{@code unknown}。
     *
     * @return 不可变的事件汇总列表
     */
    public List<JsonNode> allEvents() {
      List<JsonNode> all =
          new ArrayList<>(
              assistantMessages.size()
                  + toolUses.size()
                  + toolResults.size()
                  + userMessages.size()
                  + unknownEvents.size());
      all.addAll(assistantMessages);
      all.addAll(toolUses);
      all.addAll(toolResults);
      all.addAll(userMessages);
      all.addAll(unknownEvents);
      return Collections.unmodifiableList(all);
    }
  }
}
