package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.source.SourceRecord;
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
    List<List<Map<String, Object>>> calls = new ArrayList<>();
    for (SourceRecord record : records) {
      if (record == null) {
        continue;
      }
      String scope = scopeKey.apply(record);
      List<Map<String, Object>> units = pending.computeIfAbsent(scope, key -> new ArrayList<>());
      String type = record.eventType();
      if ("assistant".equals(type)) {
        addUnit(units, record, "assistant");
        calls.add(units);
        latest.put(scope, units);
        pending.remove(scope);
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

  private static void flushResponses(
      List<Map<String, Object>> pending, List<Map<String, Object>> previous) {
    if (previous != null
        && pending.stream().allMatch(unit -> "assistant".equals(unit.get("role")))) {
      previous.addAll(pending);
      pending.clear();
    }
  }

  private static void addUnit(List<Map<String, Object>> units, SourceRecord record, String role) {
    Map<String, Object> unit = new LinkedHashMap<>();
    unit.put("type", record.eventType());
    unit.put("role", role);
    unit.put("text", record.content());
    record.toolUseId().ifPresent(id -> unit.put("tool_call_id", id));
    units.add(Map.copyOf(unit));
  }
}
