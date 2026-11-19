package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import java.io.IOException;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 按声明身份提取工具参数，保留完整输入，不把工具结果当作输入。 */
public final class ToolInputContents {
  private ToolInputContents() {}

  /** 输入来自调用自己的 response units 或匹配声明 ID 的 catalog。 */
  public static Map<String, Input> forCall(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    Map<String, Input> inputs = inline(call);
    for (var entry : artifact.sourceUnitCatalog().values()) {
      if (!isIndependent(entry)
          && "response".equals(entry.direction().getValue())
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
  public static Map<String, Input> catalog(SourceUnitCatalogEntry entry) {
    Map<String, Input> inputs = new LinkedHashMap<>();
    if (!isIndependent(entry)
        && "response".equals(entry.direction().getValue())
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
    var content =
        com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(artifact);
    var independent = new IndependentInputs<Input>(content.header(), input -> input);
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) independent.accept(cursor.next());
    } catch (IOException exception) {
      throw new IllegalStateException("无法读取工具来源内容", exception);
    }
    for (var tool : artifact.toolExecutions())
      if ("unknown".equals(tool.declaredByCallId())) inputs.remove(tool.toolCallId());
    independent.finish().forEach(inputs::putIfAbsent);
    return inputs;
  }

  /** 独立生产单元不能由旧的 call/catalog 裸 ID 分支直接消费。 */
  public static boolean isIndependent(SourceUnitCatalogEntry entry) {
    return "independent_tool_input.v1".equals(entry.candidate())
        || entry.unitKey().startsWith("tool-input:");
  }

  /** 映射当次候选；preview 调用方只保留脱敏短文本，export 可写既有私有磁盘索引。 */
  @FunctionalInterface
  public interface InputProjection<T> {
    /** 将当前输入映射为本次消费所需的有界值。 */
    T apply(Input input) throws IOException;
  }

  /** 请求内、单遍有界的独立来源资格；必须读完整 cursor 后才允许 finish 的结果。 */
  public static final class IndependentInputs<T> {
    private static final int MAX_ITEMS = 16_384;
    private static final long MAX_CHARS = 4_194_304;
    private final InputProjection<T> projection;
    private final Map<String, Long> expected;
    private final Map<String, Long> seen = new LinkedHashMap<>();
    private final Map<String, Claim> executions = new LinkedHashMap<>();
    private final Map<String, Candidate<T>> candidates = new LinkedHashMap<>();
    private final Map<String, String> locations = new LinkedHashMap<>();
    private final Set<String> conflicts = new HashSet<>();
    private final Set<String> declarations = new HashSet<>();
    private long items;
    private long chars;
    private long inputChars;
    private long nodes;
    private boolean exceeded;

    /** 创建仅属于当前完整内容遍历的资格收集器。 */
    public IndependentInputs(
        com.feipi.session.browser.domain.normalized.NormalizedContentHeader header,
        InputProjection<T> projection) {
      this.projection = java.util.Objects.requireNonNull(projection);
      this.expected = header.totals();
      for (String key :
          List.of(
              "calls",
              "toolExecutions",
              "sourceFiles",
              "diagnostics",
              "sourceUnitCatalog",
              "sourceUnitSequenceEntries")) seen.put(key, 0L);
    }

    /** 消费当前单元；任何超限会取消整个独立结果，不返回前缀。 */
    public void accept(NormalizedContentUnit unit) throws IOException {
      if (exceeded) return;
      seen.merge("calls", (long) unit.calls().size(), Long::sum);
      seen.merge("toolExecutions", (long) unit.toolExecutions().size(), Long::sum);
      seen.merge("sourceFiles", (long) unit.sourceFiles().size(), Long::sum);
      seen.merge("diagnostics", (long) unit.diagnostics().size(), Long::sum);
      seen.merge("sourceUnitCatalog", (long) unit.sourceUnitCatalog().size(), Long::sum);
      for (var sequence : unit.sourceUnitSequences())
        seen.merge("sourceUnitSequenceEntries", (long) sequence.keys().size(), Long::sum);
      items +=
          1L + unit.calls().size() + unit.toolExecutions().size() + unit.sourceUnitCatalog().size();
      if (items > MAX_ITEMS) {
        exceeded = true;
        return;
      }
      if (seen.get("sourceUnitSequenceEntries") > 65_536) {
        exceeded = true;
        return;
      }
      for (var call : unit.calls()) {
        for (var source : call.sourceUnits())
          if (!"user".equals(source.get("role"))) observeOther(source, 0, new int[] {1024});
        for (String id : call.response().toolCallIds()) {
          if (++items > MAX_ITEMS) {
            exceeded = true;
            return;
          }
          if (!metadata(id)) return;
          declarations.add(id);
        }
      }
      for (var tool : unit.toolExecutions()) {
        if (!metadata(
            tool.toolCallId(), tool.name(), tool.declaredByCallId(), tool.subagentId().orElse("")))
          return;
        var claim =
            new Claim(
                tool.name(),
                tool.scope().getValue(),
                tool.subagentId().orElse(""),
                tool.declaredByCallId());
        if (executions.putIfAbsent(tool.toolCallId(), claim) != null)
          conflicts.add(tool.toolCallId());
      }
      for (var item : unit.sourceUnitCatalog().entrySet()) {
        var entry = item.getValue();
        if (!isIndependent(entry)) {
          if ("response".equals(entry.direction().getValue()))
            observeOther(entry.payload(), 0, new int[] {1024});
          continue;
        }
        if (!(entry.payload() instanceof Map<?, ?> payload)) continue;
        String id = string(payload.get("id"));
        if (id.isEmpty()) continue;
        if (!metadata(
            id,
            item.getKey(),
            entry.unitKey(),
            entry.originPath(),
            entry.canonicalSourceLocator(),
            entry.candidate())) return;
        String previousLocation = locations.putIfAbsent(entry.unitKey(), id);
        if (previousLocation != null) {
          conflicts.add(previousLocation);
          conflicts.add(id);
        }
        var parsed = candidate(item.getKey(), entry, payload);
        if (parsed == null || candidates.containsKey(id)) {
          conflicts.add(id);
          continue;
        }
        candidates.put(id, parsed);
      }
    }

    /** 输入不全或全局超限时无资格；不会输出已读前缀或任选重复候选。 */
    public Map<String, T> finish() {
      var result = new LinkedHashMap<String, T>();
      if (exceeded
          || seen.entrySet().stream()
              .anyMatch(
                  entry -> !entry.getValue().equals(expected.getOrDefault(entry.getKey(), 0L))))
        return result;
      candidates.forEach(
          (id, candidate) -> {
            var tool = executions.get(id);
            if (tool != null
                && !conflicts.contains(id)
                && !declarations.contains(id)
                && "unknown".equals(tool.owner())
                && tool.name().equals(candidate.claim().name())
                && tool.scope().equals(candidate.claim().scope())
                && tool.actor().equals(candidate.claim().actor()))
              result.put(id, candidate.value());
          });
      return result;
    }

    private Candidate<T> candidate(String key, SourceUnitCatalogEntry entry, Map<?, ?> payload)
        throws IOException {
      if (!payload.keySet().equals(Set.of("type", "id", "name", "input", "independent"))
          || !"tool_use".equals(payload.get("type"))
          || !"tool_use".equals(entry.unitType())
          || !"independent_tool_input.v1".equals(entry.candidate())
          || !"response".equals(entry.direction().getValue())
          || !(payload.get("input") instanceof String input)
          || input.isBlank()
          || !(payload.get("name") instanceof String name)
          || name.isBlank()
          || !(payload.get("independent") instanceof Map<?, ?> proof)
          || !proof.keySet().equals(Set.of("ordinal", "slot", "scope", "subagent"))) return null;
      if (input.length() > 65_536 || (inputChars += input.length()) > MAX_CHARS) {
        exceeded = true;
        return null;
      }
      long ordinal = integral(proof.get("ordinal"));
      long slot = integral(proof.get("slot"));
      String scope = string(proof.get("scope"));
      String actor = string(proof.get("subagent"));
      String id = string(payload.get("id"));
      if (!metadata(name, scope, actor, string(proof.get("ordinal")), string(proof.get("slot"))))
        return null;
      if (ordinal < 0
          || slot < 0
          || slot > Integer.MAX_VALUE
          || entry.partIndex() != slot
          || !entry.unitKey().equals(key)
          || !key.equals(
              "tool-input:" + ordinal + ":" + slot + ":" + entry.canonicalSourceLocator())
          || !entry.label().filter(id::equals).isPresent()
          || !entry
              .canonicalSourceLocator()
              .matches(
                  java.util.regex.Pattern.quote(entry.originPath())
                      + "#event\\["
                      + entry.eventOrder()
                      + "\\](?:\\[\\d+\\])?")
          || !("main".equals(scope) && actor.isEmpty()
              || "subagent".equals(scope)
                  && !actor.isBlank()
                  && !actor.startsWith("unknown-sidechain:")
                  && !"unknown".equals(actor))
          || entry.text().filter(value -> !value.isEmpty()).isPresent()
          || entry.preview().isPresent()
          || !entry.diagnostics().isEmpty()
          || entry.byteRange().start() != 0
          || entry.byteRange().end() != 0
          || !entry.contentHash().isEmpty()
          || entry.subSource().isPresent()
          || entry.sourceCandidate().isPresent()) return null;
      String previousSlot = locations.putIfAbsent("slot:" + ordinal + ":" + slot, id);
      if (previousSlot != null) {
        conflicts.add(previousSlot);
        conflicts.add(id);
      }
      return new Candidate<>(
          new Claim(name, scope, actor, "unknown"), projection.apply(new Input(id, name, input)));
    }

    private static long integral(Object value) {
      if (!(value instanceof String text) || !text.matches("0|[1-9][0-9]{0,18}")) return -1;
      try {
        return Long.parseLong(text);
      } catch (NumberFormatException exception) {
        return -1;
      }
    }

    private boolean metadata(String... values) {
      for (String value : values) {
        if (value.length() > 1024 || (chars += value.length()) > MAX_CHARS) {
          exceeded = true;
          return false;
        }
      }
      return true;
    }

    private void observeOther(Object value, int depth, int[] budget) {
      if (depth > 8 || budget[0]-- <= 0 || ++nodes > 262_144) {
        exceeded = true;
        return;
      }
      if (!(value instanceof Map<?, ?> map)) return;
      if (List.of("tool_use", "function_call", "custom_tool_call")
          .contains(string(map.get("type")))) {
        for (String field : List.of("id", "call_id", "tool_call_id")) {
          String id = string(map.get(field));
          if (!id.isEmpty()) {
            if (metadata(id)) conflicts.add(id);
            break;
          }
        }
      }
      if (map.get("content") instanceof List<?> blocks)
        for (var block : blocks) observeOther(block, depth + 1, budget);
    }

    /**
     * 规范化执行身份，不包含正文或来源路径。
     *
     * @param name 工具名称
     * @param scope 执行所属上下文范围
     * @param actor 子 Agent 实例标识；主上下文为空
     * @param owner 声明此执行的模型调用标识；未知时为 unknown
     */
    private record Claim(String name, String scope, String actor, String owner) {}

    /**
     * 已验证来源 envelope 的本次消费值。
     *
     * @param claim 规范化执行身份
     * @param value 当前消费端投影值
     */
    private record Candidate<T>(Claim claim, T value) {}
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
