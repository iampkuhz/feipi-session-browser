package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 事件分类器。
 *
 * <p>将源中性记录列表按 {@code eventType} 分类为归一化引擎可处理的各类别。分类结果为不可变集合，供 {@link CallBuilder} 和 {@link
 * NormalizationEngine} 使用。
 */
public final class EventClassifier {

  /** 防止实例化。 */
  private EventClassifier() {}

  /**
   * 将记录列表按类型分类。
   *
   * @param records 源中性记录列表
   * @return 分类后的记录集合
   */
  public static ClassifiedEvents classify(List<? extends SourceRecord> records) {
    if (records == null || records.isEmpty()) {
      return ClassifiedEvents.empty();
    }

    EventBuckets buckets = new EventBuckets();
    records.stream().filter(java.util.Objects::nonNull).forEach(buckets::accept);
    return buckets.toClassifiedEvents();
  }

  /** 按源中性事件类型收集分类结果的内部容器。 */
  private static final class EventBuckets {
    private final List<SourceRecord> assistantMessages = new ArrayList<>();
    private final List<SourceRecord> toolUses = new ArrayList<>();
    private final List<SourceRecord> toolResults = new ArrayList<>();
    private final List<SourceRecord> userMessages = new ArrayList<>();
    private final List<SourceRecord> unknownEvents = new ArrayList<>();

    private void accept(SourceRecord record) {
      switch (record.eventType()) {
        case "assistant" -> assistantMessages.add(record);
        case "tool_use" -> toolUses.add(record);
        case "tool_result" -> toolResults.add(record);
        case "user" -> userMessages.add(record);
        default -> unknownEvents.add(record);
      }
    }

    private ClassifiedEvents toClassifiedEvents() {
      return new ClassifiedEvents(
          List.copyOf(assistantMessages),
          List.copyOf(toolUses),
          List.copyOf(toolResults),
          List.copyOf(userMessages),
          List.copyOf(unknownEvents));
    }
  }

  /** 分类后的事件集合。 */
  public static final class ClassifiedEvents {
    private final List<SourceRecord> assistantMessages;
    private final List<SourceRecord> toolUses;
    private final List<SourceRecord> toolResults;
    private final List<SourceRecord> userMessages;
    private final List<SourceRecord> unknownEvents;

    private static final ClassifiedEvents EMPTY =
        new ClassifiedEvents(List.of(), List.of(), List.of(), List.of(), List.of());

    ClassifiedEvents(
        List<SourceRecord> assistantMessages,
        List<SourceRecord> toolUses,
        List<SourceRecord> toolResults,
        List<SourceRecord> userMessages,
        List<SourceRecord> unknownEvents) {
      this.assistantMessages = assistantMessages;
      this.toolUses = toolUses;
      this.toolResults = toolResults;
      this.userMessages = userMessages;
      this.unknownEvents = unknownEvents;
    }

    static ClassifiedEvents empty() {
      return EMPTY;
    }

    /**
     * 返回助手消息记录。
     *
     * @return 不可变助手消息记录列表
     */
    public List<SourceRecord> assistantMessages() {
      return assistantMessages;
    }

    /**
     * 返回独立工具调用记录。
     *
     * @return 不可变工具调用记录列表
     */
    public List<SourceRecord> toolUses() {
      return toolUses;
    }

    /**
     * 返回工具结果记录。
     *
     * @return 不可变工具结果记录列表
     */
    public List<SourceRecord> toolResults() {
      return toolResults;
    }

    /**
     * 返回用户消息记录。
     *
     * @return 不可变用户消息记录列表
     */
    public List<SourceRecord> userMessages() {
      return userMessages;
    }

    /**
     * 返回未知类型记录。
     *
     * @return 不可变未知记录列表
     */
    public List<SourceRecord> unknownEvents() {
      return unknownEvents;
    }

    /**
     * 返回已分类记录总数。
     *
     * @return 各分类记录数量之和
     */
    public int totalCount() {
      return assistantMessages.size()
          + toolUses.size()
          + toolResults.size()
          + userMessages.size()
          + unknownEvents.size();
    }

    /**
     * 判断分类结果是否为空。
     *
     * @return 无任何记录时返回 {@code true}
     */
    public boolean isEmpty() {
      return totalCount() == 0;
    }

    /**
     * 返回所有分类记录的汇总列表。
     *
     * @return 不可变汇总列表
     */
    public List<SourceRecord> allEvents() {
      List<SourceRecord> all =
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
