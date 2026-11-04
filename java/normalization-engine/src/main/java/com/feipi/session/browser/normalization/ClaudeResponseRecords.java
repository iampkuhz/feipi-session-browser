package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** 合并 Claude 同一源文件/子作用域内的显式 message.id 分片；usage 已由 adapter 按原始字段裁定。 */
final class ClaudeResponseRecords {
  private ClaudeResponseRecords() {}

  static List<SourceRecord> merge(List<SourceRecord> records) {
    Map<MessageKey, List<SourceRecord>> groups = new LinkedHashMap<>();
    for (SourceRecord record : records) {
      key(record)
          .ifPresent(key -> groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(record));
    }
    // 归因冲突组不参与归并，原记录仍原序保留，不能移动跨标志的首尾文本。
    groups
        .values()
        .removeIf(
            group ->
                group.stream()
                    .anyMatch(
                        fragment -> fragment.metaContext() != group.getFirst().metaContext()));
    List<SourceRecord> result = new ArrayList<>();
    Set<MessageKey> mergedKeys = new HashSet<>();
    for (SourceRecord record : records) {
      List<SourceRecord> group = key(record).map(groups::get).orElse(List.of());
      if (group.isEmpty() || group.size() == 1) {
        result.add(record);
      } else if (mergedKeys.add(key(record).orElseThrow())) {
        result.add(mergeGroup(group));
      }
    }
    return List.copyOf(result);
  }

  private static Optional<MessageKey> key(SourceRecord record) {
    if (!"assistant".equals(record.eventType())) {
      return Optional.empty();
    }
    int marker = record.locator().lastIndexOf("#event[");
    String source = marker < 0 ? record.locator() : record.locator().substring(0, marker);
    return record
        .responseMessageId()
        .filter(id -> !id.isBlank())
        .map(id -> new MessageKey(source, record.relation(), id));
  }

  private static SourceRecord mergeGroup(List<SourceRecord> group) {
    SourceRecord first = group.getFirst();
    StringBuilder content = new StringBuilder();
    Map<String, SourceToolCall> tools = new LinkedHashMap<>();
    Optional<String> stopReason = Optional.empty();
    for (SourceRecord record : group) {
      if (!record.content().isEmpty()) {
        if (!content.isEmpty()) {
          content.append('\n');
        }
        content.append(record.content());
      }
      for (SourceToolCall tool : record.toolCalls()) {
        SourceToolCall existing = tools.get(tool.toolCallId());
        if (existing == null || (!tool.input().isBlank() && !"{}".equals(tool.input()))) {
          tools.put(tool.toolCallId(), tool);
        }
      }
      if (record.responseStopReason().isPresent()) {
        stopReason = record.responseStopReason();
      }
    }
    return new SourceRecord(
        first.locator(),
        first.eventIndex(),
        first.eventType(),
        first.callId(),
        first.model(),
        first.timestamp(),
        first.turnId(),
        first.usage(),
        List.copyOf(tools.values()),
        first.toolUseId(),
        first.toolName(),
        first.toolError(),
        first.relation(),
        content.toString(),
        first.responseMessageId(),
        stopReason,
        first.timing(),
        first.metaContext());
  }

  /**
   * 同文件和父子作用域内的显式响应身份。
   *
   * @param source 来源文件身份
   * @param relation 主会话或子会话关联
   * @param messageId 上游显式响应身份
   */
  private record MessageKey(String source, SourceRecordRelation relation, String messageId) {}
}
