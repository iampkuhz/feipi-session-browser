package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;

/** 解析指定载荷，不构造局部制品，也不将完整内容展平。 */
final class ContentPayloadReader {
  private final NormalizedSessionContent content;
  private final SessionContentReader reader;
  private final ExportPayloadLookup bulk;

  ContentPayloadReader(NormalizedSessionContent content, SessionContentReader reader) {
    this(content, reader, null);
  }

  ContentPayloadReader(
      NormalizedSessionContent content, SessionContentReader reader, ExportPayloadLookup bulk) {
    this.content = content;
    this.reader = reader;
    this.bulk = bulk;
  }

  Optional<PayloadLookup.PayloadEntry> read(String id, PayloadVisibility visibility)
      throws IOException {
    java.util.Objects.requireNonNull(id, "payloadId");
    java.util.Objects.requireNonNull(visibility, "visibility");
    String[] parts = id.split(":", 3);
    if (parts.length != 3) return Optional.empty();
    if ("round".equals(parts[0])) return round(id, parts[1], parts[2], visibility);
    String text;
    PayloadSourceKind kind;
    List<PayloadLookup.ReadingBlock> reading = List.of();
    boolean unconfirmedContext = false;
    var policy = SensitiveFieldPolicy.fromVisibility(visibility);
    if ("tool".equals(parts[0])) {
      if (!List.of("input", "result").contains(parts[1])) return Optional.empty();
      var input =
          "input".equals(parts[1])
              ? toolInput(parts[2])
              : Optional.<ToolInputContents.Input>empty();
      var result = "result".equals(parts[1]) ? toolResult(parts[2]) : Optional.<String>empty();
      if (input.isEmpty() && result.isEmpty() && !hasTool(parts[2])) return Optional.empty();
      text =
          "input".equals(parts[1])
              ? input.map(ToolInputContents.Input::input).orElse("")
              : result.orElse("");
      kind =
          "input".equals(parts[1]) ? PayloadSourceKind.TOOL_INPUT : PayloadSourceKind.TOOL_RESULT;
    } else {
      if (!List.of("main", "sa").contains(parts[0]) || !List.of("req", "resp").contains(parts[1]))
        return Optional.empty();
      var found = reader.findCall(parts[2]);
      if (found.isEmpty()) return Optional.empty();
      var call = found.get();
      boolean subagent = call.scope() == CallScope.SUBAGENT;
      if (subagent != "sa".equals(parts[0])) return Optional.empty();
      boolean request = "req".equals(parts[1]);
      var view = callText(call, request);
      text = view.raw();
      reading = PayloadLookup.readingBlock(policy, view.reading().text());
      unconfirmedContext = view.reading().unconfirmedContext();
      kind =
          request
              ? subagent ? PayloadSourceKind.SUBAGENT_REQUEST : PayloadSourceKind.LLM_REQUEST
              : subagent ? PayloadSourceKind.SUBAGENT_RESPONSE : PayloadSourceKind.LLM_RESPONSE;
    }
    return Optional.of(
        new PayloadLookup.PayloadEntry(
            id, kind, parts[2], policy.applyMasking(text), false, reading, unconfirmedContext));
  }

  PayloadLookup.PayloadEntry read(
      NormalizedCall call, boolean request, PayloadVisibility visibility) throws IOException {
    java.util.Objects.requireNonNull(call, "call");
    java.util.Objects.requireNonNull(visibility, "visibility");
    boolean subagent = call.scope() == CallScope.SUBAGENT;
    String id = (subagent ? "sa" : "main") + (request ? ":req:" : ":resp:") + call.callId();
    PayloadSourceKind kind =
        request
            ? subagent ? PayloadSourceKind.SUBAGENT_REQUEST : PayloadSourceKind.LLM_REQUEST
            : subagent ? PayloadSourceKind.SUBAGENT_RESPONSE : PayloadSourceKind.LLM_RESPONSE;
    var view = callText(call, request);
    var policy = SensitiveFieldPolicy.fromVisibility(visibility);
    return new PayloadLookup.PayloadEntry(
        id,
        kind,
        call.callId(),
        policy.applyMasking(view.raw()),
        false,
        PayloadLookup.readingBlock(policy, view.reading().text()),
        view.reading().unconfirmedContext());
  }

  private Optional<PayloadLookup.PayloadEntry> round(
      String id, String side, String number, PayloadVisibility visibility) throws IOException {
    if (!List.of("req", "resp").contains(side)) return Optional.empty();
    int round;
    try {
      round = Integer.parseInt(number);
    } catch (NumberFormatException invalid) {
      return Optional.empty();
    }
    if (round < 1
        || round > reader.roundIndex().roundCount()
        || !Integer.toString(round).equals(number)) return Optional.empty();
    boolean request = "req".equals(side);
    boolean codexRequest = codexRequest(request);
    boolean main = roundHasMain(round);
    var texts = new ArrayList<RoundText>();
    var sequences = new LinkedHashMap<String, TreeMap<Integer, Integer>>();
    var tools = new LinkedHashMap<String, ToolInputContents.Input>();
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var call : units.next().calls()) {
          if (!inRound(call, round) || (main && call.scope() != CallScope.MAIN)) continue;
          var ranges =
              call.sourceUnitRefRanges().stream()
                  .filter(
                      range ->
                          range.role().isEmpty()
                              || range
                                  .role()
                                  .get()
                                  .equalsIgnoreCase(request ? "user" : "assistant"))
                  .toList();
          for (var range : ranges) {
            if (range.refs().isEmpty() && range.sequence().isPresent()) {
              sequences
                  .computeIfAbsent(range.sequence().get(), key -> new TreeMap<>())
                  .merge(range.start(), range.end(), Math::max);
            }
          }
          var inputs = new LinkedHashMap<String, ToolInputContents.Input>();
          if (!request) {
            for (var unit : call.sourceUnits()) {
              if (!"user".equals(unit.get("role"))) ToolInputContents.collect(unit, inputs);
            }
            for (String tool : call.response().toolCallIds()) tools.putIfAbsent(tool, null);
          }
          texts.add(
              new RoundText(
                  call.callKey() + " · " + call.callId(),
                  call.callKey(),
                  PayloadCallContentExtractor.resolveInline(
                      call.sourceUnits(), request ? "user" : "assistant", null, null),
                  PayloadCallContentExtractor.readingInline(call, request, codexRequest),
                  ranges,
                  inputs,
                  request ? List.of() : call.response().toolCallIds()));
        }
      }
    }
    if (texts.isEmpty()) return Optional.empty();
    var sequenceKeys = roundSequenceKeys(sequences);
    var catalogTexts = new LinkedHashMap<String, String>();
    var readingRequiresRole = new LinkedHashMap<String, Boolean>();
    var refs = new ArrayList<List<RoundRef>>();
    for (var text : texts) {
      var keys = new ArrayList<RoundRef>();
      for (var range : text.ranges()) {
        var rangeKeys =
            !range.refs().isEmpty() || range.sequence().isEmpty()
                ? range.refs()
                : sequenceKeys
                    .get(range.sequence().get())
                    .subMap(range.start(), true, range.end(), false)
                    .values();
        for (String key : rangeKeys) {
          keys.add(new RoundRef(key, range.role().isPresent()));
          catalogTexts.putIfAbsent(key, "");
        }
      }
      refs.add(keys);
    }
    var toolOrder = resolveRoundCatalog(catalogTexts, readingRequiresRole, tools, request);
    var result = new StringBuilder();
    var policy = SensitiveFieldPolicy.fromVisibility(visibility);
    var reading = new ArrayList<PayloadLookup.ReadingBlock>();
    boolean unconfirmedContext = false;
    for (int i = 0; i < texts.size(); i++) {
      RoundText call = texts.get(i);
      var visible = call.reading(refs.get(i), catalogTexts, readingRequiresRole, codexRequest);
      unconfirmedContext |= visible.unconfirmedContext();
      if (!visible.text().isEmpty())
        reading.add(
            new PayloadLookup.ReadingBlock(call.label(), policy.applyMasking(visible.text())));
      String body = call.body(refs.get(i), catalogTexts, tools, toolOrder);
      body = policy.applyMasking(body);
      if (body.isEmpty()) continue;
      if (!result.isEmpty()) result.append("\n\n");
      result.append(call.header()).append('\n').append(body);
    }
    return Optional.of(
        new PayloadLookup.PayloadEntry(
            id,
            request ? PayloadSourceKind.LLM_REQUEST : PayloadSourceKind.LLM_RESPONSE,
            "round:" + round,
            result.toString(),
            false,
            reading,
            unconfirmedContext));
  }

  private boolean inRound(NormalizedCall call, int round) {
    return reader.roundIndex().roundIndexForCall(call.callId()).orElse(0) == round;
  }

  private boolean roundHasMain(int round) throws IOException {
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var call : units.next().calls()) {
          if (inRound(call, round) && call.scope() == CallScope.MAIN) return true;
        }
      }
    }
    return false;
  }

  /** 只保存目标区间内的引用身份；合并区间避免每个调用各自重扫序列。 */
  private Map<String, TreeMap<Integer, String>> roundSequenceKeys(
      Map<String, TreeMap<Integer, Integer>> intervals) throws IOException {
    for (var ranges : intervals.values()) {
      var merged = new TreeMap<Integer, Integer>();
      for (var range : ranges.entrySet()) {
        var previous = merged.lastEntry();
        if (previous != null && previous.getValue() >= range.getKey()) {
          merged.put(previous.getKey(), Math.max(previous.getValue(), range.getValue()));
        } else merged.put(range.getKey(), range.getValue());
      }
      ranges.clear();
      ranges.putAll(merged);
    }
    var result = new LinkedHashMap<String, TreeMap<Integer, String>>();
    intervals.keySet().forEach(name -> result.put(name, new TreeMap<>()));
    if (intervals.isEmpty()) return result;
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var chunk : units.next().sourceUnitSequences()) {
          var ranges = intervals.get(chunk.name());
          if (ranges == null) continue;
          for (int i = 0; i < chunk.keys().size(); i++) {
            long position = chunk.offset() + i;
            if (position > Integer.MAX_VALUE) break;
            int offset = (int) position;
            var range = ranges.floorEntry(offset);
            if (range != null && offset < range.getValue()) {
              result.get(chunk.name()).put(offset, chunk.keys().get(i));
            }
          }
        }
      }
    }
    return result;
  }

  private Map<String, Integer> resolveRoundCatalog(
      Map<String, String> texts,
      Map<String, Boolean> readingRequiresRole,
      Map<String, ToolInputContents.Input> tools,
      boolean request)
      throws IOException {
    var names = new LinkedHashMap<String, String>();
    var order = new LinkedHashMap<String, Integer>();
    if (texts.isEmpty() && tools.isEmpty()) return order;
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        var unit = units.next();
        for (var tool : unit.toolExecutions()) {
          if (tools.containsKey(tool.toolCallId()))
            names.putIfAbsent(tool.toolCallId(), tool.name());
        }
        for (var entry : unit.sourceUnitCatalog().entrySet()) {
          var value = entry.getValue();
          if (texts.containsKey(entry.getKey())
              && ("request".equals(value.direction().getValue()) == request)
              && !List.of("tool_use", "function_call", "custom_tool_call")
                  .contains(value.unitType())) {
            String text = PayloadCallContentExtractor.catalogEntryText(value);
            texts.put(entry.getKey(), text);
            if (PayloadCallContentExtractor.isReadingEntry(value, Optional.empty(), request)) {
              readingRequiresRole.put(entry.getKey(), false);
            } else if (PayloadCallContentExtractor.isReadingEntry(
                value, Optional.of(request ? "user" : "assistant"), request)) {
              readingRequiresRole.put(entry.getKey(), true);
            } else {
              readingRequiresRole.remove(entry.getKey());
            }
          }
          if (!tools.isEmpty()
              && "response".equals(value.direction().getValue())
              && value.payload() instanceof Map<?, ?> payload) {
            var inputs = new LinkedHashMap<String, ToolInputContents.Input>();
            ToolInputContents.collect(payload, inputs);
            inputs.forEach(
                (key, input) -> {
                  if (tools.containsKey(key)) {
                    order.putIfAbsent(key, order.size());
                    tools.putIfAbsent(key, input);
                  }
                });
          }
        }
      }
    }
    tools.replaceAll(
        (key, input) ->
            input == null
                ? new ToolInputContents.Input(key, names.getOrDefault(key, "Tool"), "")
                : input);
    return order;
  }

  /**
   * 已过滤到当前正文侧的目录引用；角色证据不在调用之间共享。
   *
   * @param key 共享目录文本的索引键
   * @param hasRole 当前引用是否明确给出正文侧角色
   */
  private record RoundRef(String key, boolean hasRole) {}

  /**
   * 仅请求轮次的输出文本和引用元数据，不持有调用或源单元正文对象。
   *
   * @param header 调用的显示键和稳定身份
   * @param label 阅读区区分不同调用的简短标识
   * @param inline 目录正文缺失时使用的内联正文
   * @param inlineReading 目录无可读消息时采用的内联对话
   * @param ranges 所选正文侧的目录引用区间
   * @param inputs 已提取的内联工具输入，保留声明顺序
   * @param toolIds 响应侧声明的工具身份
   */
  private record RoundText(
      String header,
      String label,
      String inline,
      PayloadCallContentExtractor.ReadingText inlineReading,
      List<SourceUnitRefRange> ranges,
      Map<String, ToolInputContents.Input> inputs,
      List<String> toolIds) {
    PayloadCallContentExtractor.ReadingText reading(
        List<RoundRef> refs,
        Map<String, String> catalog,
        Map<String, Boolean> requiresRole,
        boolean codexRequest) {
      var text = new PayloadCallContentExtractor.ReadingText(codexRequest);
      for (var ref : refs) {
        Boolean required = requiresRole.get(ref.key());
        if (required != null && (!required || ref.hasRole())) text.add(catalog.get(ref.key()));
      }
      return text.orElse(inlineReading);
    }

    String body(
        List<RoundRef> refs,
        Map<String, String> catalog,
        Map<String, ToolInputContents.Input> tools,
        Map<String, Integer> order) {
      var text = new StringBuilder();
      for (var ref : refs) append(text, catalog.get(ref.key()));
      if (text.isEmpty()) text.append(inline);
      toolIds.stream()
          .sorted(
              java.util.Comparator.comparingInt(id -> order.getOrDefault(id, Integer.MAX_VALUE)))
          .forEach(id -> inputs.putIfAbsent(id, tools.get(id)));
      if (!inputs.isEmpty()) {
        if (!text.isEmpty()) text.append("\n\n");
        text.append("工具指令\n");
        text.append(
            String.join(
                "\n\n", inputs.values().stream().map(ToolInputContents.Input::display).toList()));
      }
      return text.toString();
    }
  }

  /**
   * 同一个调用的两种正文视图。
   *
   * @param raw 包含原有上下文和工具记录的文本
   * @param reading 按消息角色筛选后的对话正文
   */
  private record CallText(String raw, PayloadCallContentExtractor.ReadingText reading) {}

  private CallText callText(NormalizedCall call, boolean request) throws IOException {
    var text = new StringBuilder();
    boolean codexRequest = codexRequest(request);
    var reading = new PayloadCallContentExtractor.ReadingText(codexRequest);
    for (var range : call.sourceUnitRefRanges()) {
      if (range.role().isPresent()
          && !range.role().get().equalsIgnoreCase(request ? "user" : "assistant")) continue;
      forEachRef(
          range,
          ref -> {
            if (bulk != null) {
              String value = bulk.catalogText(ref, request);
              append(text, value);
              if (bulk.isReadingText(ref, range.role().isPresent())) reading.add(value);
              return;
            }
            var entry = catalog(ref);
            if (entry.isPresent()
                && ("request".equals(entry.get().direction().getValue()) == request)
                && !List.of("tool_use", "function_call", "custom_tool_call")
                    .contains(entry.get().unitType())) {
              String value = PayloadCallContentExtractor.catalogEntryText(entry.get());
              append(text, value);
              if (PayloadCallContentExtractor.isReadingEntry(entry.get(), range.role(), request)) {
                reading.add(value);
              }
            }
          });
    }
    if (text.isEmpty()) {
      text.append(
          PayloadCallContentExtractor.resolveInline(
              call.sourceUnits(), request ? "user" : "assistant", null, null));
    }
    if (!request) {
      var inputs = new LinkedHashMap<String, ToolInputContents.Input>();
      for (var unit : call.sourceUnits()) {
        if (!"user".equals(unit.get("role"))) ToolInputContents.collect(unit, inputs);
      }
      for (String toolId : call.response().toolCallIds()) {
        if (!inputs.containsKey(toolId)) {
          inputs.put(
              toolId,
              toolInput(toolId).orElseGet(() -> new ToolInputContents.Input(toolId, "Tool", "")));
        }
      }
      if (!inputs.isEmpty()) {
        if (!text.isEmpty()) text.append("\n\n");
        text.append("工具指令\n");
        text.append(
            String.join(
                "\n\n", inputs.values().stream().map(ToolInputContents.Input::display).toList()));
      }
    }
    return new CallText(
        text.toString(),
        reading.orElse(PayloadCallContentExtractor.readingInline(call, request, codexRequest)));
  }

  private boolean codexRequest(boolean request) {
    return request && content.header().agent() == NormalizedAgent.CODEX;
  }

  private Optional<SourceUnitCatalogEntry> catalog(String key) throws IOException {
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        var entry = units.next().sourceUnitCatalog().get(key);
        if (entry != null) return Optional.of(entry);
      }
    }
    return Optional.empty();
  }

  private void forEachRef(SourceUnitRefRange range, RefConsumer action) throws IOException {
    if (bulk != null) {
      bulk.forEachRef(range, action::accept);
      return;
    }
    if (!range.refs().isEmpty() || range.sequence().isEmpty()) {
      for (String key : range.refs()) action.accept(key);
      return;
    }
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var chunk : units.next().sourceUnitSequences()) {
          if (!range.sequence().get().equals(chunk.name())) continue;
          for (int i = 0; i < chunk.keys().size(); i++) {
            long offset = chunk.offset() + i;
            if (offset >= range.start() && offset < range.end()) action.accept(chunk.keys().get(i));
          }
        }
      }
    }
  }

  private Optional<ToolInputContents.Input> toolInput(String id) throws IOException {
    if (bulk != null) return bulk.input(id);
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        var unit = units.next();
        for (var call : unit.calls()) {
          for (var source : call.sourceUnits()) {
            if ("user".equals(source.get("role"))) continue;
            var inputs = new LinkedHashMap<String, ToolInputContents.Input>();
            ToolInputContents.collect(source, inputs);
            if (inputs.containsKey(id)) return Optional.of(inputs.get(id));
          }
        }
        for (var entry : unit.sourceUnitCatalog().values()) {
          if (!"response".equals(entry.direction().getValue())
              || !(entry.payload() instanceof Map<?, ?> payload)) continue;
          var inputs = new LinkedHashMap<String, ToolInputContents.Input>();
          ToolInputContents.collect(payload, inputs);
          if (inputs.containsKey(id)) return Optional.of(inputs.get(id));
        }
      }
    }
    return Optional.empty();
  }

  private Optional<String> toolResult(String id) throws IOException {
    if (bulk != null) return bulk.result(id);
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        var unit = units.next();
        for (var call : unit.calls()) {
          String inline =
              PayloadCallContentExtractor.resolveInline(
                  call.sourceUnits(), null, "tool_result", id);
          if (!inline.isEmpty()) return Optional.of(inline);
        }
      }
    }
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var entry : units.next().sourceUnitCatalog().values()) {
          Map<?, ?> payload = entry.payload() instanceof Map<?, ?> map ? map : Map.of();
          boolean result =
              "tool_result".equals(entry.unitType()) || "tool_result".equals(payload.get("type"));
          if (result
              && (entry.label().filter(id::equals).isPresent()
                  || id.equals(payload.get("tool_call_id")))) {
            return Optional.of(PayloadCallContentExtractor.catalogEntryText(entry));
          }
        }
      }
    }
    return Optional.empty();
  }

  private boolean hasTool(String id) throws IOException {
    if (bulk != null) return bulk.hasTool(id);
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        var unit = units.next();
        if (unit.toolExecutions().stream().anyMatch(tool -> id.equals(tool.toolCallId()))
            || unit.calls().stream().anyMatch(call -> call.response().toolCallIds().contains(id))) {
          return true;
        }
      }
    }
    return false;
  }

  private static void append(StringBuilder target, String text) {
    if (text.isEmpty()) return;
    if (!target.isEmpty()) target.append('\n');
    target.append(text);
  }

  /** 处理单个目录引用键，并将读取异常传递给调用方。 */
  @FunctionalInterface
  private interface RefConsumer {
    void accept(String key) throws IOException;
  }
}
