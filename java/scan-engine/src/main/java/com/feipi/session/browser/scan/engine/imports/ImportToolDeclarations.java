package com.feipi.session.browser.scan.engine.imports;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 将明确的工具执行声明引用与输入载荷补回导入调用；不生成调用、计量或推测归属。 */
final class ImportToolDeclarations {
  private ImportToolDeclarations() {}

  static List<NormalizedCall> restore(
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog) {
    Map<String, Map<String, Object>> declarations = declarations(catalog);
    Map<String, List<String>> declaredByCall = new LinkedHashMap<>();
    for (NormalizedToolExecution tool : tools) {
      if (declarations.containsKey(tool.toolCallId())) {
        declaredByCall
            .computeIfAbsent(tool.declaredByCallId(), key -> new ArrayList<>())
            .add(tool.toolCallId());
      }
    }
    return calls.stream()
        .map(
            call ->
                restore(call, declaredByCall.getOrDefault(call.callId(), List.of()), declarations))
        .toList();
  }

  private static Map<String, Map<String, Object>> declarations(
      Map<String, SourceUnitCatalogEntry> catalog) {
    Map<String, Map<String, Object>> declarations = new LinkedHashMap<>();
    for (SourceUnitCatalogEntry entry : catalog.values()) {
      if (entry.direction() != SourceUnitDirection.RESPONSE
          || !(entry.payload() instanceof Map<?, ?> payload)
          || !"tool_use".equals(payload.get("type"))
          || !(payload.get("id") instanceof String id)) {
        continue;
      }
      Map<String, Object> unit = new LinkedHashMap<>();
      payload.forEach(
          (key, value) -> {
            if (key instanceof String field) unit.put(field, value);
          });
      declarations.putIfAbsent(id, Collections.unmodifiableMap(unit));
    }
    return declarations;
  }

  private static NormalizedCall restore(
      NormalizedCall call, List<String> boundIds, Map<String, Map<String, Object>> declarations) {
    var responseIds = new ArrayList<>(call.response().toolCallIds());
    for (String id : boundIds) {
      if (!responseIds.contains(id)) responseIds.add(id);
    }
    List<Map<String, Object>> units = new ArrayList<>(call.sourceUnits());
    for (String id : responseIds) {
      Map<String, Object> declaration = declarations.get(id);
      if (declaration == null) continue;
      boolean found = false;
      for (int i = 0; i < units.size(); i++) {
        Map<String, Object> unit = units.get(i);
        Object type = unit.get("type");
        Object unitId =
            unit.getOrDefault("id", unit.getOrDefault("call_id", unit.get("tool_call_id")));
        if (type instanceof String name
            && List.of("tool_use", "function_call", "custom_tool_call").contains(name)
            && !"user".equals(unit.get("role"))
            && id.equals(unitId)) {
          var complete = new LinkedHashMap<>(unit);
          complete.put("input", declaration.get("input"));
          units.set(i, Collections.unmodifiableMap(complete));
          found = true;
        }
      }
      if (!found) units.add(declaration);
    }
    if (responseIds.equals(call.response().toolCallIds()) && units.equals(call.sourceUnits()))
      return call;
    return new NormalizedCall(
        call.callId(),
        call.callIndex(),
        call.callKey(),
        call.scope(),
        call.parentCallId(),
        call.parentToolCallId(),
        call.turnId(),
        call.model(),
        call.timestamp(),
        call.usage(),
        call.request(),
        new NormalizedCallResponse(List.copyOf(responseIds)),
        call.sourceUnitRefRanges(),
        units,
        call.attributionCandidates(),
        call.usageSource(),
        call.subagentId(),
        call.parentToolName());
  }
}
