package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedDiagnostic;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceToolObservation;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/** 保存无正文的全局调用关系；正文只由内容游标按 ordinal 重放。 */
final class ManagedNormalizationPlan {
  SourceRecordSequence records;
  final List<Frame> frames = new ArrayList<>();
  final List<Fact> facts = new ArrayList<>();
  final Map<String, String> consumers = new LinkedHashMap<>();
  final Map<String, String> declarations = new LinkedHashMap<>();
  final Map<String, Long> errors = new LinkedHashMap<>();
  final ToolObservations observations = new ToolObservations();
  final List<ToolRef> tools = new ArrayList<>();
  final List<Long> observedInputs = new ArrayList<>();
  final List<Long> resultOrdinals = new ArrayList<>();
  List<NormalizedSourceFile> sourceFiles;
  Map<String, SourceUnitCatalogEntry> catalog;
  List<NormalizedDiagnostic> diagnostics;
  NormalizedContentHeader header;

  private ManagedNormalizationPlan(
      SourceRecordSequence records, List<NormalizedSourceFile> sourceFiles) {
    this.records = Objects.requireNonNull(records);
    this.sourceFiles = List.copyOf(sourceFiles);
    this.catalog = NormalizationEngine.buildSourceUnitCatalog(sourceFiles);
  }

  /**
   * 预先确定全局关系和完整元数据，不持有 SourceRecord。
   *
   * @param records 借用的可重放源序列
   * @param diagnostics 输入诊断
   * @param sourceFiles 来源文件
   * @return 无正文计划
   * @throws IOException 源读取失败
   */
  static ManagedNormalizationPlan create(
      SourceRecordSequence records,
      List<SourceDiagnostic> diagnostics,
      List<NormalizedSourceFile> sourceFiles)
      throws IOException {
    var plan = new ManagedNormalizationPlan(records, sourceFiles);
    plan.scan(diagnostics);
    if (plan.frames.isEmpty()) {
      try (var cursor = plan.records.openCursor()) {
        long ordinal = 0;
        while (cursor.hasNext()) {
          if (ObservedInputContents.isUser(cursor.next())) plan.observedInputs.add(ordinal);
          ordinal++;
        }
      }
    }
    plan.relations();
    plan.units();
    plan.metadata();
    return plan;
  }

  private final UnknownEventDiagnostics.Collector unknown =
      new UnknownEventDiagnostics.Collector(NormalizedAgent.CODEX);
  private final SessionTimingCalculator.Accumulator timing =
      new SessionTimingCalculator.Accumulator();
  private final EventActivityAccumulator eventActivity =
      new EventActivityAccumulator(NormalizedAgent.CODEX);
  private final Set<String> userMessages = new HashSet<>();
  private final Set<String> assistantMessages = new HashSet<>();
  private Optional<String> start = Optional.empty();
  private Optional<String> end = Optional.empty();
  private Instant startInstant;
  private Instant endInstant;
  private long codexTools;

  private void scan(List<SourceDiagnostic> inputDiagnostics) throws IOException {
    var identities = new ToolIdentityPlan(sourceFiles);
    Map<Long, SourceToolObservation> pendingObservations = new LinkedHashMap<>();
    Map<String, Integer> rounds = new HashMap<>();
    try (var cursor = records.openCursor()) {
      long ordinal = 0;
      while (cursor.hasNext()) {
        SourceRecord record = cursor.next();
        identities.accept(ordinal, record);
        long observationOrdinal = ordinal;
        record
            .toolObservation()
            .ifPresent(value -> pendingObservations.put(observationOrdinal, value));
        String type = record.eventType();
        var fact =
            new Fact(
                ordinal++,
                type,
                CallBuilder.recordScopeKey(record),
                record.callId(),
                record.toolUseId(),
                record.toolName(),
                record.toolCalls().stream()
                    .map(t -> new ToolIdentity(t.toolCallId(), t.name()))
                    .toList(),
                record.toolError().isPresent(),
                !record.content().isEmpty(),
                record.metaContext(),
                CallBuilder.callScope(record),
                CallBuilder.displaySubagentId(record));
        facts.add(fact);
        if (ToolResultContents.isResult(record)) resultOrdinals.add(fact.ordinal());
        timing.accept(record);
        eventActivity.accept(record);
        observe(record);
        if ("assistant".equals(type)) {
          var subagent = CallBuilder.displaySubagentId(record);
          String callId =
              subagent
                  .map(id -> id + "-SR" + rounds.merge(id, 1, Integer::sum))
                  .orElseGet(() -> CallBuilder.extractCallId(record, frames.size() + 1));
          frames.add(new Frame(fact, frames.size() + 1, callId, record));
        } else if (!List.of("tool_use", "tool_result", "user").contains(type)) {
          unknown.accept(record);
        }
        if ("tool_result".equals(type) && record.toolError().isPresent()) {
          record.toolUseId().ifPresent(id -> errors.put(id, fact.ordinal()));
        }
        if ("tool_use".equals(type)
            && List.of("function_call", "custom_tool_call").contains(record.turnId().orElse("")))
          codexTools++;
      }
    }
    identities.finish();
    pendingObservations.forEach(
        (ordinal, value) ->
            identities
                .observation(ordinal, Optional.of(value))
                .ifPresent(planValue -> observations.accept(planValue)));
    records = identities.borrow(records);
    sourceFiles = identities.sourceFiles();
    catalog = NormalizationEngine.buildSourceUnitCatalog(sourceFiles);
    for (int i = 0; i < facts.size(); i++) {
      var old = facts.get(i);
      String scope =
          identities.scope(
              old.ordinal(),
              old.scope(),
              old.type(),
              old.callId(),
              old.toolUseId(),
              old.toolName(),
              old.subagent());
      var projectedTools = new ArrayList<ToolIdentity>();
      for (int index = 0; index < old.tools().size(); index++) {
        var tool = old.tools().get(index);
        int slot =
            "tool_use".equals(old.type()) && old.callId().filter(tool.id()::equals).isPresent()
                ? -1
                : index;
        projectedTools.add(
            new ToolIdentity(identities.id(old.ordinal(), slot, tool.id()), tool.name()));
      }
      facts.set(
          i,
          new Fact(
              old.ordinal(),
              old.type(),
              scope,
              "tool_use".equals(old.type())
                  ? old.callId().map(raw -> identities.id(old.ordinal(), -1, raw))
                  : old.callId(),
              old.toolUseId().map(raw -> identities.id(old.ordinal(), -2, raw)),
              old.toolName(),
              projectedTools,
              old.hasError(),
              old.hasContent(),
              old.metaContext(),
              scope.equals(old.scope()) ? old.executionScope() : CallScope.SUBAGENT,
              old.subagent()));
    }
    for (Frame frame : frames) {
      frame.fact = facts.get((int) frame.fact.ordinal());
      var relation =
          identities.relation(
              frame.fact.ordinal(),
              new com.feipi.session.browser.domain.source.SourceRecordRelation(
                  frame.subagent,
                  Optional.empty(),
                  frame.parentTool,
                  frame.parent,
                  frame.parentToolName));
      frame.parentTool = relation.parentToolCallId();
      frame.parent = relation.parentCallId();
    }
    errors.clear();
    for (Fact fact : facts) {
      if ("tool_result".equals(fact.type()) && fact.hasError())
        fact.toolUseId().ifPresent(id -> errors.put(id, fact.ordinal()));
    }
    var all = new ArrayList<Map<String, Object>>();
    inputDiagnostics.forEach(d -> all.add(NormalizationEngine.toMap(d)));
    all.addAll(unknown.diagnostics());
    all.addAll(identities.diagnostics);
    diagnostics = all.stream().map(NormalizedDiagnostic::fromMap).toList();
  }

  private void observe(SourceRecord record) {
    if (!record.metaContext()
        && record.toolUseId().isEmpty()
        && record.relation().subagentId().isEmpty()
        && !record.locator().replace('\\', '/').contains("/subagents/")) {
      String locator = record.locator();
      int suffix = locator.lastIndexOf("#event[");
      String identity =
          (suffix < 0 ? locator : locator.substring(0, suffix))
              + "#event["
              + record.eventIndex()
              + "]";
      record.messageRole().filter("user"::equals).ifPresent(role -> userMessages.add(identity));
      record
          .messageRole()
          .filter("assistant"::equals)
          .ifPresent(role -> assistantMessages.add(identity));
    }
    record
        .timestamp()
        .filter(s -> !s.isBlank())
        .ifPresent(
            value -> {
              try {
                Instant instant = Instant.parse(value);
                if (startInstant == null || instant.isBefore(startInstant)) {
                  startInstant = instant;
                  start = Optional.of(value);
                }
                if (endInstant == null || instant.isAfter(endInstant)) {
                  endInstant = instant;
                  end = Optional.of(value);
                }
              } catch (java.time.DateTimeException ignored) {
                // 无法解析的时间仍保留在调用，不作为会话时间范围。
              }
            });
  }

  private void relations() {
    Map<String, List<Frame>> scopes = new HashMap<>();
    for (Frame frame : frames)
      scopes.computeIfAbsent(frame.fact.scope(), k -> new ArrayList<>()).add(frame);
    Map<String, Integer> next = new HashMap<>();
    Map<String, Frame> latest = new HashMap<>();
    // 只保存每个来源/scope 的边界状态，不缓存正文或逐工具重放源。
    var pendingInput = new java.util.HashSet<String>();
    var pendingOwners = new java.util.HashSet<String>();
    int assistantIndex = 0;
    for (Fact fact : facts) {
      if ("user".equals(fact.type())) {
        if (!fact.metaContext() && pendingOwners.contains(fact.scope())) {
          throw new IllegalArgumentException("TOOL_OWNER_UNAVAILABLE");
        }
        pendingInput.add(fact.scope());
      } else if ("assistant".equals(fact.type())) {
        pendingInput.remove(fact.scope());
        pendingOwners.remove(fact.scope());
      } else if ("tool_use".equals(fact.type()) && pendingInput.contains(fact.scope())) {
        pendingOwners.add(fact.scope());
      }
      List<Frame> scopeFrames = scopes.getOrDefault(fact.scope(), List.of());
      if (scopeFrames.isEmpty()) continue;
      int position = next.getOrDefault(fact.scope(), 0);
      if ("assistant".equals(fact.type())) {
        Frame frame = frames.get(assistantIndex++);
        next.put(fact.scope(), position + 1);
        latest.put(fact.scope(), frame);
        for (ToolIdentity tool : fact.tools()) declarations.put(tool.id(), frame.id);
      } else if ("tool_result".equals(fact.type()) && position < scopeFrames.size()) {
        String consumer = scopeFrames.get(position).id;
        fact.toolUseId().ifPresent(id -> consumers.put(id, consumer));
      } else if ("tool_use".equals(fact.type())) {
        Frame current = latest.get(fact.scope());
        Frame owner =
            current == null
                    || pendingInput.contains(fact.scope())
                    || (current.closing() && position < scopeFrames.size())
                ? scopeFrames.get(Math.min(position, scopeFrames.size() - 1))
                : current;
        fact.callId().ifPresent(id -> declarations.put(id, owner.id));
      }
    }
    if (!pendingOwners.isEmpty()) {
      throw new IllegalArgumentException("TOOL_OWNER_UNAVAILABLE");
    }
    Map<String, List<Frame>> byId = new HashMap<>();
    Map<String, String> fallbackCalls = new HashMap<>();
    for (Frame frame : frames) {
      byId.computeIfAbsent(frame.id, k -> new ArrayList<>()).add(frame);
      fallbackCalls.put(frame.fact.scope(), frame.id);
      frame.parent =
          frame.parent.or(() -> frame.parentTool.map(declarations::get)).filter(v -> !v.isBlank());
      for (int i = 0; i < frame.fact.tools().size(); i++)
        tools.add(
            new ToolRef(
                frame.fact, i, frame.id, frame.fact.executionScope(), frame.fact.subagent()));
    }
    declarations.forEach(
        (id, owner) -> {
          for (Frame frame : byId.getOrDefault(owner, List.of())) frame.declaredTools.add(id);
        });
    for (Fact fact : facts) {
      if ("tool_result".equals(fact.type()))
        fact.toolUseId()
            .ifPresent(
                id -> {
                  for (Frame frame : byId.getOrDefault(consumers.get(id), List.of()))
                    frame.results.add(id);
                });
      if ("tool_use".equals(fact.type())
          && fact.callId().isPresent()
          && fact.toolName().isPresent()) {
        String fallback = fallbackCalls.getOrDefault(fact.scope(), "unknown");
        // standalone scope/subagent 使用原记录规则，输出时逐条投影。
        tools.add(
            new ToolRef(
                fact,
                -1,
                declarations.getOrDefault(fact.callId().get(), fallback),
                fact.executionScope(),
                fact.subagent()));
      }
    }
  }

  private void units() {
    Map<String, List<UnitRef>> pending = new LinkedHashMap<>();
    Map<String, List<UnitRef>> pendingTools = new HashMap<>();
    Map<String, Frame> latest = new HashMap<>();
    int frameIndex = 0;
    for (Fact fact : facts) {
      List<UnitRef> units = pending.computeIfAbsent(fact.scope(), k -> new ArrayList<>());
      Frame current = latest.get(fact.scope());
      switch (fact.type()) {
        case "assistant" -> {
          Frame frame = frames.get(frameIndex++);
          units.add(new UnitRef(fact.ordinal(), -1, "assistant"));
          appendTools(units, fact);
          units.addAll(pendingTools.getOrDefault(fact.scope(), List.of()));
          pendingTools.remove(fact.scope());
          frame.units = units;
          latest.put(fact.scope(), frame);
          pending.remove(fact.scope());
        }
        case "tool_use" -> {
          boolean newInput = units.stream().anyMatch(u -> "user".equals(u.role()));
          if (current != null && !current.closing() && !newInput) appendTools(current.units, fact);
          else
            appendTools(pendingTools.computeIfAbsent(fact.scope(), k -> new ArrayList<>()), fact);
        }
        case "user", "tool_result" -> {
          flush(units, current);
          units.add(new UnitRef(fact.ordinal(), -1, "user"));
        }
        case "response_item" -> {
          if (fact.hasContent()) units.add(new UnitRef(fact.ordinal(), -1, "assistant"));
        }
        default -> {}
      }
    }
    pending.forEach((scope, units) -> flush(units, latest.get(scope)));
  }

  private static void appendTools(List<UnitRef> units, Fact fact) {
    for (int i = 0; i < fact.tools().size(); i++)
      units.add(new UnitRef(fact.ordinal(), i, "assistant"));
  }

  private static void flush(List<UnitRef> units, Frame current) {
    if (current != null && units.stream().allMatch(u -> "assistant".equals(u.role()))) {
      current.units.addAll(units);
      units.clear();
    }
  }

  private void metadata() {
    Map<String, Object> session = new LinkedHashMap<>();
    session.put("agent", "codex");
    session.put(
        "eventCount",
        records.recordCount() <= Integer.MAX_VALUE
            ? (Object) (int) records.recordCount()
            : records.recordCount());
    long fresh = 0, read = 0, write = 0, output = 0;
    Set<String> declared = new HashSet<>(), consumed = new HashSet<>(), executed = new HashSet<>();
    for (Frame frame : frames) {
      fresh += frame.usage.fresh();
      read += frame.usage.cacheRead();
      write += frame.usage.cacheWrite();
      output += frame.usage.output();
      declared.addAll(frame.declaredTools);
      consumed.addAll(frame.results);
    }
    long failed = 0;
    for (ToolRef tool : tools) {
      String id =
          tool.index() < 0
              ? tool.fact().callId().orElseThrow()
              : tool.fact().tools().get(tool.index()).id();
      executed.add(id);
      if (tool.fact().hasError() || errors.containsKey(id)) failed++;
    }
    session.put("totalTokens", fresh + read + write + output);
    session.put("declaredTools", declared.size());
    session.put("executedTools", executed.size());
    session.put("consumedResults", consumed.size());
    session.put("failedToolCount", failed);
    session.put("userMessageCount", (long) userMessages.size());
    session.put("assistantMessageCount", (long) assistantMessages.size());
    session.put("userMessageCountMeasured", !userMessages.isEmpty());
    session.put("assistantMessageCountMeasured", !assistantMessages.isEmpty());
    session.put("toolCallCount", Math.max(codexTools, tools.size()));
    Optional<String> callStart =
        frames.stream().flatMap(f -> f.timestamp.stream()).filter(v -> !v.isBlank()).findFirst();
    Optional<String> callEnd =
        frames.reversed().stream()
            .flatMap(f -> f.timestamp.stream())
            .filter(v -> !v.isBlank())
            .findFirst();
    start = start.or(() -> callStart);
    end = end.or(() -> callEnd);
    start.ifPresent(v -> session.put("started_at", v));
    end.ifPresent(v -> session.put("ended_at", v));
    Double wall = null;
    if (start.isPresent() && end.isPresent())
      try {
        double duration =
            Duration.between(Instant.parse(start.get()), Instant.parse(end.get())).toMillis()
                / 1000.0;
        if (duration >= 0) {
          wall = duration;
          session.put("duration_seconds", duration);
        }
      } catch (java.time.DateTimeException ignored) {
      }
    var timingResult = timing.finish(wall);
    session.putAll(timingResult.toMetadata());
    session.put(
        "modelExecutionSeconds",
        timingResult.modelExecutionSeconds() == null ? 0.0 : timingResult.modelExecutionSeconds());
    session.put(
        "toolExecutionSeconds",
        timingResult.toolExecutionSeconds() == null ? 0.0 : timingResult.toolExecutionSeconds());
    frames.stream()
        .map(f -> f.model)
        .filter(v -> !v.isEmpty())
        .findFirst()
        .ifPresent(v -> session.put("model", v));
    var unknownDiagnostics = unknown.diagnostics();
    if (!unknownDiagnostics.isEmpty())
      session.put(
          "unknownEventDiagnosticCoverage",
          Map.of(
              "occurrences",
              unknownDiagnostics.stream()
                  .mapToLong(d -> ((Number) d.get("occurrenceCount")).longValue())
                  .sum(),
              "groups",
              unknownDiagnostics.size(),
              "grouping",
              "sourceLocator,eventType,eventMsgSubtype",
              "positionUnit",
              "sourceEventIndex"));
    session.put("eventActivity", eventActivity.snapshot());
    header =
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            NormalizedSessionMetadata.fromMap(session),
            Map.of(
                "calls",
                (long) frames.size(),
                "toolExecutions",
                (long) tools.size(),
                "diagnostics",
                (long) diagnostics.size(),
                "sourceFiles",
                (long) sourceFiles.size(),
                "sourceUnitCatalog",
                (long) catalog.size() + observedInputs.size() + resultOrdinals.size(),
                "sourceUnitSequenceEntries",
                0L));
  }

  /**
   * 不含正文或工具输入的记录关系事实。
   *
   * @param ordinal 全局序列位置
   * @param type 源事件类型
   * @param scope 源记录的关联作用域
   * @param callId 源调用或工具标识
   * @param toolUseId 工具结果引用标识
   * @param toolName 独立工具名称
   * @param tools 不含输入正文的工具身份
   * @param hasError 是否有错误正文
   * @param hasContent 是否有非空正文
   * @param metaContext 是否为显式元上下文输入，不结束真实用户段
   * @param executionScope 工具执行的归一化作用域
   * @param subagent 子代理展示标识
   */
  record Fact(
      long ordinal,
      String type,
      String scope,
      Optional<String> callId,
      Optional<String> toolUseId,
      Optional<String> toolName,
      List<ToolIdentity> tools,
      boolean hasError,
      boolean hasContent,
      boolean metaContext,
      CallScope executionScope,
      Optional<String> subagent) {}

  /**
   * 工具的稳定身份。
   *
   * @param id 工具调用标识
   * @param name 工具名称
   */
  record ToolIdentity(String id, String name) {}

  /**
   * 源单元重放位置，负工具索引表示正文。
   *
   * @param ordinal 记录的全局序列位置
   * @param toolIndex 记录内的工具索引，负值表示正文
   * @param role 原有源单元角色
   */
  record UnitRef(long ordinal, int toolIndex, String role) {}

  /**
   * 工具执行重放位置，负索引表示独立声明。
   *
   * @param fact 不含正文的声明事实
   * @param index 工具索引，负值表示独立声明
   * @param owner 声明调用标识
   * @param scope 执行作用域
   * @param subagent 子代理展示标识
   */
  record ToolRef(Fact fact, int index, String owner, CallScope scope, Optional<String> subagent) {}

  /** 只保存调用标量和正文位置的计划帧。 */
  static final class Frame {
    Fact fact;
    final int index;
    final String id;
    final CallScope scope;
    final Optional<String> subagent;
    Optional<String> parent;
    Optional<String> parentTool;
    final Optional<String> parentToolName;
    final Optional<String> turn;
    final String model;
    final Optional<String> timestamp;
    final NormalizedCallUsage usage;
    final Map<String, String> provenance;
    final List<String> results = new ArrayList<>();
    final List<String> declaredTools = new ArrayList<>();
    List<UnitRef> units = new ArrayList<>();

    /**
     * 从当前源记录提取调用标量，不保存记录或任何正文引用。
     *
     * @param fact 不含正文的记录关系事实
     * @param index 从一开始的全局调用序号
     * @param id 已确定的调用标识
     * @param record 仅在构造期间借用的当前源记录
     */
    Frame(Fact fact, int index, String id, SourceRecord record) {
      this.fact = fact;
      this.index = index;
      this.id = id;
      this.subagent = fact.subagent();
      this.scope = subagent.isPresent() ? CallScope.SUBAGENT : CallScope.MAIN;
      this.parent = subagent.isPresent() ? record.relation().parentCallId() : Optional.empty();
      this.parentTool =
          subagent.isPresent() ? record.relation().parentToolCallId() : Optional.empty();
      this.parentToolName =
          subagent.isPresent() ? record.relation().parentToolName() : Optional.empty();
      this.turn = record.turnId();
      this.model = record.model().orElse("");
      this.timestamp = record.timestamp();
      this.usage = TokenAccountant.extractUsage(record);
      this.provenance = record.usage().provenance();
    }

    boolean closing() {
      return TokenAccountant.isUsageClosingFrame(fact.callId().orElse(""));
    }
  }
}
