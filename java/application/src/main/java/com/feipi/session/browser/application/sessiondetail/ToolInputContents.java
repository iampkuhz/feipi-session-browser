package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 按声明身份提取工具参数，保留完整输入，不把工具结果当作输入。 */
public final class ToolInputContents {
  private ToolInputContents() {}

  /** 输入来自调用自己的 response units 或匹配声明 ID 的 catalog。 */
  public static Map<String, Input> forCall(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    Map<String, Input> inputs = inline(call);
    for (var entry : artifact.sourceUnitCatalog().values()) {
      if ("response".equals(entry.direction().getValue())
          && entry.payload() instanceof Map<?, ?> payload) {
        Map<String, Input> candidates = new LinkedHashMap<>();
        collect(payload, candidates);
        candidates.forEach(
            (id, input) -> {
              if (call.response().toolCallIds().contains(id)) {
                inputs.putIfAbsent(id, input);
              }
            });
      }
    }
    // 历史制品可能只有声明 ID；明确提示重建，而非空 response。
    for (String id : call.response().toolCallIds()) {
      inputs.computeIfAbsent(id, key -> new Input(key, toolName(key, artifact), ""));
    }
    return inputs;
  }

  /**
   * 只取调用内联的工具声明，不读取目录或把请求侧工具结果误当成参数。
   *
   * @param call 归一化调用
   * @return 按源顺序排列的工具输入
   */
  public static Map<String, Input> inline(NormalizedCall call) {
    Map<String, Input> inputs = new LinkedHashMap<>();
    for (Map<String, Object> unit : call.sourceUnits()) {
      if (!"user".equals(unit.get("role"))) collect(unit, inputs);
    }
    inputs.keySet().retainAll(call.response().toolCallIds());
    return inputs;
  }

  /** 只解析响应方向的目录声明；调用方仍须按 response tool ID 选取，不按同名工具匹配。 */
  public static Map<String, Input> catalog(
      com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry entry) {
    Map<String, Input> inputs = new LinkedHashMap<>();
    if ("response".equals(entry.direction().getValue())
        && entry.payload() instanceof Map<?, ?> payload) collect(payload, inputs);
    return inputs;
  }

  /** 为所有已声明工具建立内容索引，供 API 和 payload 共用。 */
  public static Map<String, Input> all(NormalizedSessionArtifact artifact) {
    Map<String, Input> inputs = new LinkedHashMap<>();
    for (NormalizedCall call : artifact.calls()) {
      forCall(call, artifact)
          .forEach(
              (id, input) -> {
                Input previous = inputs.get(id);
                if (previous == null || previous.input().isEmpty()) {
                  inputs.put(id, input);
                }
              });
    }
    return inputs;
  }

  static void collect(Map<?, ?> unit, Map<String, Input> inputs) {
    String type = string(unit.get("type"));
    if (List.of("tool_use", "function_call", "custom_tool_call").contains(type)) {
      String id = string(unit.get("id"));
      if (id.isEmpty()) id = string(unit.get("call_id"));
      if (id.isEmpty()) id = string(unit.get("tool_call_id"));
      if (!id.isEmpty()) {
        Object raw = unit.containsKey("input") ? unit.get("input") : unit.get("arguments");
        String input = raw == null ? "" : String.valueOf(raw);
        inputs.putIfAbsent(id, new Input(id, string(unit.get("name")), input));
      }
    }
    if (unit.get("content") instanceof List<?> blocks) {
      for (Object block : blocks) {
        if (block instanceof Map<?, ?> map) collect(map, inputs);
      }
    }
  }

  private static String toolName(String id, NormalizedSessionArtifact artifact) {
    return artifact.toolExecutions().stream()
        .filter(tool -> id.equals(tool.toolCallId()))
        .map(tool -> tool.name())
        .findFirst()
        .orElse("Tool");
  }

  private static String string(Object value) {
    return value instanceof String text ? text : "";
  }

  /**
   * 参数原文仅用于可见内容展示，不执行、不写日志。
   *
   * @param id 工具声明的稳定标识
   * @param name 工具名称
   * @param input 参数原文，缺失时为空字符串
   */
  public record Input(String id, String name, String input) {
    /** 以稳定 ID 对齐声明与结果。 */
    public String display() {
      return (name.isBlank() ? "Tool" : name)
          + " ["
          + id
          + "]\n"
          + (input.isEmpty() ? "输入未记录（旧索引可能需要重新扫描）" : input);
    }
  }
}
