package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/** 按流顺序与作用域分配增量内容，不复制完整历史或回填未来输入。 */
final class CallSourceUnitBuilder {
  private CallSourceUnitBuilder() {}

  static List<List<Map<String, Object>>> build(
      List<? extends SourceRecord> records, Function<SourceRecord, String> scopeKey) {
    Map<String, List<Map<String, Object>>> pending = new LinkedHashMap<>();
    Map<String, List<Map<String, Object>>> latest = new LinkedHashMap<>();
    Map<String, List<Map<String, Object>>> pendingTools = new LinkedHashMap<>();
    Map<String, Boolean> closingFrames = new LinkedHashMap<>();
    List<List<Map<String, Object>>> calls = new ArrayList<>();
    for (SourceRecord record : records) {
      if (record == null) {
        continue;
      }
      String scope = scopeKey.apply(record);
      List<Map<String, Object>> units = pending.computeIfAbsent(scope, key -> new ArrayList<>());
      String type = record.eventType();
      addReadingEvidence(units, record);
      if ("assistant".equals(type)) {
        addAssistantUnits(units, record);
        units.addAll(pendingTools.getOrDefault(scope, List.of()));
        pendingTools.remove(scope);
        calls.add(units);
        latest.put(scope, units);
        closingFrames.put(scope, TokenAccountant.isUsageClosingFrame(record.callId().orElse("")));
        pending.remove(scope);
      } else if ("tool_use".equals(type)) {
        List<Map<String, Object>> current = latest.get(scope);
        boolean newInput = units.stream().anyMatch(unit -> "user".equals(unit.get("role")));
        if (current != null && !closingFrames.getOrDefault(scope, false) && !newInput) {
          addToolUnits(current, record);
        } else {
          // 独立声明属于同 scope 下一响应帧，不能被 tool_result/user 边界回填到上一调用。
          addToolUnits(pendingTools.computeIfAbsent(scope, key -> new ArrayList<>()), record);
        }
      } else if ("user".equals(type) || "tool_result".equals(type)) {
        flushResponses(units, latest.get(scope));
        addUnit(units, record, "user");
      } else if ("response_item".equals(type) && !record.content().isEmpty()) {
        addUnit(units, record, "assistant");
      }
    }
    // Codex 的最后一条 response_item 可晚于最后一个 token_count；新输入绝不能倒灌。
    pending.forEach((scope, units) -> flushResponses(units, latest.get(scope)));
    return calls.stream().map(List::copyOf).toList();
  }

  /**
   * 为 assistant 记录添加源单元。
   *
   * <p>文本内容作为 assistant 单元写入（即使为空，以保持调用边界）；独立工具单元保留声明事件时间。
   */
  private static void addAssistantUnits(List<Map<String, Object>> units, SourceRecord record) {
    addUnit(units, record, "assistant");
    addToolUnits(units, record);
  }

  private static void addToolUnits(List<Map<String, Object>> units, SourceRecord record) {
    for (SourceToolCall tool : record.toolCalls()) units.add(toolUnit(record, tool));
  }

  static Map<String, Object> toolUnit(SourceRecord record, SourceToolCall tool) {
    Map<String, Object> unit = new LinkedHashMap<>();
    unit.put("type", "tool_use");
    unit.put("role", "assistant");
    unit.put("text", "");
    unit.put("id", tool.toolCallId());
    unit.put("name", tool.name());
    unit.put("input", tool.input());
    record
        .timestamp()
        .filter(value -> !value.isBlank())
        .ifPresent(value -> unit.put("timestamp", value));
    return Map.copyOf(unit);
  }

  private static void flushResponses(
      List<Map<String, Object>> pending, List<Map<String, Object>> previous) {
    if (previous != null
        && pending.stream().allMatch(unit -> "assistant".equals(unit.get("role")))) {
      previous.addAll(pending);
      pending.clear();
    }
  }

  static void addReadingEvidence(List<Map<String, Object>> units, SourceRecord record) {
    for (var evidence : record.readingEvidence()) {
      units.add(
          Map.of(
              "type",
              "codex_context_" + evidence.kind(),
              "role",
              "context",
              "text",
              evidence.text()));
    }
  }

  private static void addUnit(List<Map<String, Object>> units, SourceRecord record, String role) {
    Map<String, Object> unit = new LinkedHashMap<>();
    unit.put("type", record.eventType());
    unit.put("role", role);
    unit.put("text", record.content());
    if (record.metaContext()) {
      unit.put("isMeta", true);
    }
    record.toolUseId().ifPresent(id -> unit.put("tool_call_id", id));
    units.add(Map.copyOf(unit));
  }
}
