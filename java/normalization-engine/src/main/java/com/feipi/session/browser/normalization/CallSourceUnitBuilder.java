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
    return buildAssigned(records, scopeKey).calls();
  }

  static Assigned buildAssigned(
      List<? extends SourceRecord> records, Function<SourceRecord, String> scopeKey) {
    var frameIds = CallBuilder.sourceFrameIds(records);
    var consumers = CallBuilder.mapToolResultOccurrences(records, frameIds, scopeKey);
    int frameIndex = 0;
    var resultTargets = new java.util.IdentityHashMap<Map<String, Object>, String>();
    var occurrences = new java.util.IdentityHashMap<Map<String, Object>, Occurrence>();
    Map<String, List<Map<String, Object>>> pending = new LinkedHashMap<>();
    Map<String, List<Map<String, Object>>> latest = new LinkedHashMap<>();
    Map<String, List<Map<String, Object>>> deferredResults = new LinkedHashMap<>();
    Map<String, List<Occurrence>> pendingTools = new LinkedHashMap<>();
    Map<String, Boolean> closingFrames = new LinkedHashMap<>();
    List<List<Map<String, Object>>> calls = new ArrayList<>();
    for (int ordinal = 0; ordinal < records.size(); ordinal++) {
      SourceRecord record = records.get(ordinal);
      if (record == null) {
        continue;
      }
      String scope = scopeKey.apply(record);
      List<Map<String, Object>> units = pending.computeIfAbsent(scope, key -> new ArrayList<>());
      String type = record.eventType();
      if ("assistant".equals(type)) {
        String frameId = frameIds.get(frameIndex++);
        // 延后输入与待归回响应分开，不能让结果阻断晚到响应的原边界。
        units.addAll(0, deferredResults.getOrDefault(scope, List.of()));
        deferredResults.remove(scope);
        var deferred = new ArrayList<Map<String, Object>>();
        units.removeIf(
            unit -> {
              if ("tool_result".equals(unit.get("type"))
                  && !frameId.equals(resultTargets.get(unit))) {
                deferred.add(unit);
                return true;
              }
              return false;
            });
        addUnit(units, record, "assistant", ordinal);
        addToolUnits(units, occurrences(record, ordinal), occurrences);
        addToolUnits(units, pendingTools.getOrDefault(scope, List.of()), occurrences);
        pendingTools.remove(scope);
        calls.add(units);
        latest.put(scope, units);
        closingFrames.put(scope, TokenAccountant.isUsageClosingFrame(record.callId().orElse("")));
        pending.remove(scope);
        if (!deferred.isEmpty()) deferredResults.put(scope, deferred);
      } else if ("tool_use".equals(type)) {
        List<Map<String, Object>> current = latest.get(scope);
        boolean newInput = units.stream().anyMatch(unit -> "user".equals(unit.get("role")));
        if (current != null && !closingFrames.getOrDefault(scope, false) && !newInput) {
          addToolUnits(current, occurrences(record, ordinal), occurrences);
        } else {
          // 独立声明属于同 scope 下一响应帧，不能被 tool_result/user 边界回填到上一调用。
          pendingTools
              .computeIfAbsent(scope, key -> new ArrayList<>())
              .addAll(occurrences(record, ordinal));
        }
      } else if ("user".equals(type) || "tool_result".equals(type)) {
        flushResponses(units, latest.get(scope));
        if (!"tool_result".equals(type)) {
          addUnit(units, record, "user", ordinal);
        } else if (consumers.containsKey((long) ordinal)) {
          var unit = addUnit(units, record, "user", ordinal);
          resultTargets.put(unit, consumers.get((long) ordinal));
        }
      } else if ("response_item".equals(type) && !record.content().isEmpty()) {
        addUnit(units, record, "assistant", ordinal);
      }
    }
    // Codex 的最后一条 response_item 可晚于最后一个 token_count；新输入绝不能倒灌。
    pending.forEach((scope, units) -> flushResponses(units, latest.get(scope)));
    return new Assigned(
        calls.stream().map(List::copyOf).toList(),
        occurrences,
        pendingTools.entrySet().stream()
            .filter(entry -> !latest.containsKey(entry.getKey()))
            .flatMap(entry -> entry.getValue().stream())
            .sorted(
                java.util.Comparator.comparingInt(Occurrence::ordinal)
                    .thenComparingInt(Occurrence::slot))
            .toList());
  }

  /**
   * 单个来源工具槽位。
   *
   * @param ordinal 记录顺序，不按事件坐标去重
   * @param record 实际分配的来源记录
   * @param slot 记录内工具槽位
   */
  record Occurrence(int ordinal, SourceRecord record, int slot) {}

  /**
   * 分配后的单元与按对象身份关联的来源位置。
   *
   * @param calls 各调用的真实分配单元
   * @param occurrences 单元对象对应的工具来源
   * @param independent EOF 仍未分配给调用的真实工具来源
   */
  record Assigned(
      List<List<Map<String, Object>>> calls,
      Map<Map<String, Object>, Occurrence> occurrences,
      List<Occurrence> independent) {}

  private static List<Occurrence> occurrences(SourceRecord record, int ordinal) {
    var result = new ArrayList<Occurrence>();
    for (int slot = 0; slot < record.toolCalls().size(); slot++) {
      result.add(new Occurrence(ordinal, record, slot));
    }
    return result;
  }

  private static void addToolUnits(
      List<Map<String, Object>> units,
      List<Occurrence> tools,
      Map<Map<String, Object>, Occurrence> occurrences) {
    for (var occurrence : tools) {
      SourceToolCall tc = occurrence.record().toolCalls().get(occurrence.slot());
      Map<String, Object> unit = new LinkedHashMap<>();
      unit.put("type", "tool_use");
      unit.put("role", "assistant");
      unit.put("text", "");
      unit.put("id", tc.toolCallId());
      unit.put("name", tc.name());
      unit.put("input", tc.input());
      var assigned = Map.copyOf(unit);
      units.add(assigned);
      occurrences.put(assigned, occurrence);
    }
  }

  private static void flushResponses(
      List<Map<String, Object>> pending, List<Map<String, Object>> previous) {
    if (previous != null
        && pending.stream().allMatch(unit -> "assistant".equals(unit.get("role")))) {
      previous.addAll(pending);
      pending.clear();
    }
  }

  private static Map<String, Object> addUnit(
      List<Map<String, Object>> units, SourceRecord record, String role, long ordinal) {
    Map<String, Object> unit = new LinkedHashMap<>();
    if (ToolResultContents.isResult(record)) {
      unit.put("result_source_unit_key", ToolResultContents.sourceUnitKey(record, ordinal));
    }
    unit.put("type", record.eventType());
    unit.put("role", role);
    unit.put("text", record.content());
    if (record.metaContext()) {
      unit.put("isMeta", true);
    }
    record.toolUseId().ifPresent(id -> unit.put("tool_call_id", id));
    var assigned = Map.copyOf(unit);
    units.add(assigned);
    return assigned;
  }
}
