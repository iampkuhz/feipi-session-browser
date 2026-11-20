package com.feipi.session.browser.scan.engine.imports;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.normalization.NormalizationEngine.ToolBinding;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** 将明确的工具执行声明引用与输入载荷补回导入调用；不生成调用、计量或推测归属。 */
final class ImportToolDeclarations {
  private ImportToolDeclarations() {}

  /** 只消费实际分配的坐标，在固定位置核对原声明后复用完整镜像。 */
  static List<NormalizedCall> bind(
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog,
      List<ToolBinding> bindings,
      String path) {
    var owners = new LinkedHashMap<String, List<NormalizedCall>>();
    calls.forEach(
        call -> owners.computeIfAbsent(call.callId(), key -> new ArrayList<>()).add(call));
    var unitOwners = new IdentityHashMap<Map<String, Object>, List<NormalizedCall>>();
    var responseIds = new IdentityHashMap<NormalizedCall, Set<String>>();
    for (var call : calls) {
      responseIds.put(call, new HashSet<>(call.response().toolCallIds()));
      for (var unit : call.sourceUnits()) {
        unitOwners.computeIfAbsent(unit, ignored -> new ArrayList<>()).add(call);
      }
    }
    var executions = new LinkedHashMap<String, List<NormalizedToolExecution>>();
    tools.forEach(
        tool -> executions.computeIfAbsent(tool.toolCallId(), key -> new ArrayList<>()).add(tool));
    var candidates = new LinkedHashMap<String, List<ToolBinding>>();
    for (var binding : bindings) {
      String key = path + "#raw[" + binding.eventIndex() + "]/tool";
      candidates.computeIfAbsent(key, ignored -> new ArrayList<>()).add(binding);
    }
    var refs = new LinkedHashMap<String, List<String>>();
    candidates.forEach(
        (key, values) -> {
          if (values.size() != 1) return;
          var binding = values.getFirst();
          if (binding.toolSlot() != 0
              || !binding.locator().equals(path + "#event[" + binding.eventIndex() + "]")) return;
          var entry = catalog.get(key);
          if (entry == null
              || !(entry.payload() instanceof Map<?, ?> raw)
              || !binding.rawId().equals(raw.get("id"))
              || !binding.rawName().equals(raw.get("name"))
              || !binding.rawInput().equals(raw.get("input"))) return;
          var assignedCalls = owners.getOrDefault(binding.callId(), List.of());
          if (assignedCalls.size() != 1) return;
          var call = assignedCalls.getFirst();
          var matching = executions.getOrDefault((String) binding.unit().get("id"), List.of());
          var assignedOwners = unitOwners.getOrDefault(binding.unit(), List.of());
          if (matching.size() != 1
              || assignedOwners.size() != 1
              || !assignedOwners.getFirst().equals(call)) return;
          var tool = matching.getFirst();
          if (!tool.declaredByCallId().equals(call.callId())
              || tool.scope() != binding.scope()
              || call.scope() != binding.scope()
              || !tool.subagentId().equals(binding.subagentId())
              || !call.subagentId().equals(binding.subagentId())
              || !tool.name().equals(binding.rawName())
              || !responseIds.get(call).contains(tool.toolCallId())) return;
          catalog.put(
              key,
              new SourceUnitCatalogEntry(
                  entry.unitKey(),
                  entry.originPath(),
                  entry.canonicalSourceLocator(),
                  entry.unitType(),
                  entry.candidate(),
                  entry.direction(),
                  entry.eventOrder(),
                  entry.partIndex(),
                  entry.byteRange(),
                  entry.contentHash(),
                  entry.timestamp(),
                  Optional.of(tool.toolCallId()),
                  entry.priority(),
                  entry.preview(),
                  entry.text(),
                  binding.unit(),
                  entry.subSource(),
                  entry.sourceCandidate(),
                  entry.diagnostics()));
          refs.computeIfAbsent(call.callId(), ignored -> new ArrayList<>()).add(key);
        });
    return calls.stream()
        .map(
            call -> {
              var keys = refs.getOrDefault(call.callId(), List.of());
              if (keys.isEmpty()) return call;
              var ranges = new ArrayList<>(call.sourceUnitRefRanges());
              ranges.add(
                  new SourceUnitRefRange(Optional.empty(), 0, 0, keys, Optional.of("assistant")));
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
                  call.response(),
                  ranges,
                  call.sourceUnits(),
                  call.attributionCandidates(),
                  call.usageSource(),
                  call.subagentId(),
                  call.parentToolName());
            })
        .toList();
  }

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
