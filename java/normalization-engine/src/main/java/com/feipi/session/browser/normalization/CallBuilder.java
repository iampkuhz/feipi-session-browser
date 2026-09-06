package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceToolCall;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.IntStream;
import java.util.stream.Stream;

/** 调用构建器。 */
public final class CallBuilder {

  /** 防止实例化。 */
  private CallBuilder() {}

  /**
   * 从源中性记录列表和分类记录构建归一化调用列表。
   *
   * @param records 源中性记录列表（保持事件流顺序）
   * @param classified 分类后的记录
   * @return 不可变的 {@link NormalizedCall} 列表，按遍历顺序排列
   */
  public static List<NormalizedCall> buildCalls(
      List<? extends SourceRecord> records, EventClassifier.ClassifiedEvents classified) {
    CallBuildContext context = CallBuildContext.create(records, classified.assistantMessages());
    List<List<Map<String, Object>>> units =
        CallSourceUnitBuilder.build(records, record -> displaySubagentId(record).orElse(""));
    return IntStream.range(0, context.frames().size())
        .mapToObj(
            index ->
                buildCall(
                    context,
                    classified.toolResults(),
                    context.frames().get(index),
                    units.get(index)))
        .toList();
  }

  /**
   * 从源中性记录列表和分类记录构建工具执行边列表。
   *
   * @param records 源中性记录列表（保持事件流顺序）
   * @param classified 分类后的记录
   * @param calls 已构建的调用列表
   * @return 不可变的 {@link NormalizedToolExecution} 列表
   */
  public static List<NormalizedToolExecution> buildToolExecutions(
      List<? extends SourceRecord> records,
      EventClassifier.ClassifiedEvents classified,
      List<NormalizedCall> calls) {
    ExecutionContext context =
        ExecutionContext.create(records, classified.assistantMessages(), calls);
    Map<String, String> toolErrors = buildToolErrorMap(classified.toolResults());
    return Stream.concat(
            assistantToolExecutions(context, toolErrors).stream(),
            standaloneToolExecutions(
                classified.toolUses(),
                calls,
                context.toolResultConsumers(),
                toolErrors,
                context.toolDeclarations())
                .stream())
        .toList();
  }

  private static NormalizedCall buildCall(
      CallBuildContext context,
      List<SourceRecord> toolResults,
      AssistantCallFrame frame,
      List<Map<String, Object>> sourceUnits) {
    SourceRecord record = frame.record();
    NormalizedCallUsage usage = TokenAccountant.extractUsage(record);

    return new NormalizedCall(
        frame.callId(),
        frame.index(),
        "C" + frame.index(),
        frame.scope(),
        frame.parentCallId(),
        frame.parentToolCallId(),
        record.turnId(),
        record.model().orElse(""),
        record.timestamp(),
        usage,
        new NormalizedCallRequest(
            toolResultIdsForCall(toolResults, context.toolResultConsumers(), frame.callId())),
        new NormalizedCallResponse(
            record.toolCalls().stream().map(SourceToolCall::toolCallId).toList()),
        List.of(),
        sourceUnits,
        Map.of(),
        Map.of(),
        frame.subagentId(),
        frame.parentToolName());
  }

  private static List<String> toolResultIdsForCall(
      List<SourceRecord> toolResults, Map<String, String> consumers, String callId) {
    List<String> ids = new ArrayList<>();
    for (SourceRecord record : toolResults) {
      record
          .toolUseId()
          .filter(toolUseId -> callId.equals(consumers.get(toolUseId)))
          .ifPresent(ids::add);
    }
    return List.copyOf(ids);
  }

  private static List<NormalizedToolExecution> assistantToolExecutions(
      ExecutionContext context, Map<String, String> toolErrors) {
    return context.frames().stream()
        .flatMap(frame -> assistantToolExecutions(context.toolResultConsumers(), toolErrors, frame))
        .toList();
  }

  private static Stream<NormalizedToolExecution> assistantToolExecutions(
      Map<String, String> consumers, Map<String, String> toolErrors, AssistantCallFrame frame) {
    return frame.record().toolCalls().stream()
        .map(
            toolCall ->
                toolExecution(
                    toolCall.toolCallId(),
                    toolCall.name(),
                    frame.callId(),
                    Optional.ofNullable(consumers.get(toolCall.toolCallId())),
                    Optional.ofNullable(toolErrors.get(toolCall.toolCallId())),
                    frame.scope(),
                    frame.subagentId()));
  }

  private static List<NormalizedToolExecution> standaloneToolExecutions(
      List<SourceRecord> toolUses,
      List<NormalizedCall> calls,
      Map<String, String> consumers,
      Map<String, String> toolErrors,
      Map<String, String> declarations) {
    List<NormalizedToolExecution> executions = new ArrayList<>();
    for (SourceRecord toolUseRecord : toolUses) {
      Optional<String> toolCallId = toolUseRecord.callId();
      Optional<String> toolName = toolUseRecord.toolName();
      if (toolCallId.isEmpty() || toolName.isEmpty()) {
        continue;
      }
      executions.add(
          toolExecution(
              toolCallId.get(),
              toolName.get(),
              declarations.getOrDefault(toolCallId.get(), declaredByLastCall(calls)),
              Optional.ofNullable(consumers.get(toolCallId.get())),
              toolUseRecord.toolError(),
              callScope(toolUseRecord),
              toolExecutionSubagentId(toolUseRecord)));
    }
    return executions;
  }

  private static NormalizedToolExecution toolExecution(
      String toolCallId,
      String name,
      String declaredByCallId,
      Optional<String> consumedByCallId,
      Optional<String> errorStatus,
      CallScope scope,
      Optional<String> subagentId) {
    return new NormalizedToolExecution(
        toolCallId,
        name,
        scope,
        declaredByCallId,
        consumedByCallId,
        errorStatus,
        Optional.empty(),
        0L,
        List.of(),
        subagentId);
  }

  /**
   * 从工具结果记录构建 toolCallId → error 映射。
   *
   * @param toolResults 工具结果记录列表
   * @return 工具调用标识到错误信息的映射
   */
  private static Map<String, String> buildToolErrorMap(List<SourceRecord> toolResults) {
    Map<String, String> errors = new LinkedHashMap<>();
    for (SourceRecord record : toolResults) {
      record
          .toolUseId()
          .filter(id -> record.toolError().isPresent())
          .ifPresent(id -> errors.put(id, record.toolError().get()));
    }
    return errors;
  }

  private static String declaredByLastCall(List<NormalizedCall> calls) {
    return calls.isEmpty() ? "unknown" : calls.get(calls.size() - 1).callId();
  }

  private static Map<String, String> mapToolResultConsumers(
      List<? extends SourceRecord> records, List<String> callIds) {
    Map<String, String> map = new LinkedHashMap<>();
    if (callIds.isEmpty()) {
      return map;
    }

    int nextAssistantIndex = 0;
    String lastCallId = callIds.get(callIds.size() - 1);
    for (SourceRecord record : records) {
      if (record == null) {
        continue;
      }
      if ("assistant".equals(record.eventType())) {
        nextAssistantIndex = Math.min(nextAssistantIndex + 1, callIds.size());
      } else if ("tool_result".equals(record.eventType())) {
        putConsumer(map, record, callIds, nextAssistantIndex, lastCallId);
      }
    }
    return map;
  }

  private static void putConsumer(
      Map<String, String> map,
      SourceRecord record,
      List<String> callIds,
      int nextAssistantIndex,
      String lastCallId) {
    record
        .toolUseId()
        .ifPresent(
            toolUseId ->
                map.put(
                    toolUseId,
                    nextAssistantIndex < callIds.size()
                        ? callIds.get(nextAssistantIndex)
                        : lastCallId));
  }

  private static Map<String, String> mapToolDeclarations(
      List<? extends SourceRecord> records, List<String> callIds) {
    Map<String, String> map = new LinkedHashMap<>();
    if (callIds.isEmpty()) {
      return map;
    }
    int nextAssistantIndex = 0;
    String currentAssistantCallId = "";
    for (SourceRecord record : records) {
      if (record == null) {
        continue;
      }
      if ("assistant".equals(record.eventType())) {
        currentAssistantCallId = callIds.get(Math.min(nextAssistantIndex, callIds.size() - 1));
        nextAssistantIndex = Math.min(nextAssistantIndex + 1, callIds.size());
        String owner = currentAssistantCallId;
        for (SourceToolCall toolCall : record.toolCalls()) {
          map.put(toolCall.toolCallId(), owner);
        }
      } else if ("tool_use".equals(record.eventType())) {
        String owner = declaredToolOwner(callIds, nextAssistantIndex, currentAssistantCallId);
        record.callId().ifPresent(toolCallId -> map.put(toolCallId, owner));
      }
    }
    return map;
  }

  private static String declaredToolOwner(
      List<String> callIds, int nextAssistantIndex, String currentAssistantCallId) {
    if (currentAssistantCallId.isBlank()) {
      return callIds.get(Math.min(nextAssistantIndex, callIds.size() - 1));
    }
    if (currentAssistantCallId.startsWith("token_count:") && nextAssistantIndex < callIds.size()) {
      return callIds.get(nextAssistantIndex);
    }
    return currentAssistantCallId;
  }

  private static String extractCallId(SourceRecord record, int fallbackIndex) {
    return record.callId().orElse("C" + fallbackIndex);
  }

  private static CallScope callScope(SourceRecord record) {
    boolean relationSubagent = relationValue(record, SourceRecordRelation::subagentId).isPresent();
    Optional<String> parentToolCallId =
        relationValue(record, SourceRecordRelation::parentToolCallId);
    boolean parentSpawnTool =
        "spawn_agent".equals(record.toolName().orElse(""))
            && parentToolCallId.isPresent()
            && record.callId().equals(parentToolCallId);
    if (relationSubagent && !parentSpawnTool) {
      return CallScope.SUBAGENT;
    }
    return subagentId(record).isPresent() ? CallScope.SUBAGENT : CallScope.MAIN;
  }

  private static Optional<String> displaySubagentId(SourceRecord record) {
    return relationValue(record, SourceRecordRelation::subagentId)
        .or(() -> subagentId(record).map(id -> "agent-" + id));
  }

  private static Optional<String> toolExecutionSubagentId(SourceRecord record) {
    return displaySubagentId(record);
  }

  private static Optional<String> subagentId(SourceRecord record) {
    String locator = record.locator().replace('\\', '/');
    int marker = locator.lastIndexOf("/subagents/");
    if (marker < 0) {
      return Optional.empty();
    }
    String tail = locator.substring(marker + "/subagents/".length());
    int hash = tail.indexOf('#');
    if (hash >= 0) {
      tail = tail.substring(0, hash);
    }
    int slash = tail.indexOf('/');
    if (slash >= 0) {
      tail = tail.substring(0, slash);
    }
    if (tail.endsWith(".jsonl")) {
      tail = tail.substring(0, tail.length() - ".jsonl".length());
    }
    if (tail.startsWith("agent-")) {
      tail = tail.substring("agent-".length());
    }
    return tail.isBlank() ? Optional.empty() : Optional.of(tail);
  }

  /**
   * 表示 AssistantCallFrame 数据。
   *
   * @param index 顺序索引。
   * @param record 原始记录对象。
   * @param callId 调用标识符。
   * @param scope 调用作用域。
   * @param parentCallId 父调用标识符。
   * @param subagentId subagent 标识符。
   * @param parentToolCallId 父工具调用标识符。
   * @param parentToolName 父工具名。
   */
  private record AssistantCallFrame(
      /* 顺序索引 */
      @PositiveOrZero int index,
      /* 原始记录对象 */
      @NotNull SourceRecord record,
      /* 调用标识符 */
      @NotNull String callId,
      /* 调用作用域 */
      @NotNull CallScope scope,
      /* 父调用标识符 */
      @NotNull Optional<String> parentCallId,
      /* 子代理实例标识符 */
      @NotNull Optional<String> subagentId,
      /* 父工具调用标识符 */
      @NotNull Optional<String> parentToolCallId,
      /* 父工具名 */
      @NotNull Optional<String> parentToolName) {
    public AssistantCallFrame {
      ValidationSupport.validateCanonicalConstructor(
          AssistantCallFrame.class,
          index,
          record,
          callId,
          scope,
          parentCallId,
          subagentId,
          parentToolCallId,
          parentToolName);
    }
  }

  /**
   * 表示 CallBuildContext 数据。
   *
   * @param frames assistant 调用帧列表。
   * @param toolResultConsumers tool result 消费者映射。
   */
  private record CallBuildContext(
      /* assistant 调用帧列表 */
      @NotNull List<AssistantCallFrame> frames,
      /* tool result 消费者映射 */
      @NotNull Map<String, String> toolResultConsumers) {

    private static CallBuildContext create(
        List<? extends SourceRecord> records, List<SourceRecord> assistantMessages) {
      List<AssistantCallFrame> frames = assistantFrames(assistantMessages);
      Map<String, String> declarations = mapToolDeclarations(records, callIds(frames));
      frames = attachParentCallIds(frames, declarations);
      return new CallBuildContext(frames, mapToolResultConsumers(records, callIds(frames)));
    }

    public CallBuildContext {
      ValidationSupport.validateCanonicalConstructor(
          CallBuildContext.class, frames, toolResultConsumers);
      toolResultConsumers = Map.copyOf(toolResultConsumers);
    }

    private static List<AssistantCallFrame> attachParentCallIds(
        List<AssistantCallFrame> frames, Map<String, String> declarations) {
      List<AssistantCallFrame> result = new ArrayList<>(frames.size());
      for (AssistantCallFrame frame : frames) {
        Optional<String> parentCallId =
            frame
                .parentCallId()
                .or(() -> frame.parentToolCallId().map(declarations::get))
                .filter(value -> value != null && !value.isBlank());
        result.add(
            new AssistantCallFrame(
                frame.index(),
                frame.record(),
                frame.callId(),
                frame.scope(),
                parentCallId,
                frame.subagentId(),
                frame.parentToolCallId(),
                frame.parentToolName()));
      }
      return List.copyOf(result);
    }

    private static List<AssistantCallFrame> assistantFrames(List<SourceRecord> assistantMessages) {
      List<AssistantCallFrame> frames = new ArrayList<>();
      Map<String, Integer> subagentCounters = new LinkedHashMap<>();
      for (int index = 0; index < assistantMessages.size(); index++) {
        SourceRecord record = assistantMessages.get(index);
        Optional<String> subagent = displaySubagentId(record);
        Optional<String> parentToolCallId =
            relationValue(record, SourceRecordRelation::parentToolCallId);
        Optional<String> parentToolName =
            relationValue(record, SourceRecordRelation::parentToolName);
        if (subagent.isPresent()) {
          String id = subagent.get();
          int subRound = subagentCounters.merge(id, 1, Integer::sum);
          frames.add(
              new AssistantCallFrame(
                  index + 1,
                  record,
                  id + "-SR" + subRound,
                  CallScope.SUBAGENT,
                  relationValue(record, SourceRecordRelation::parentCallId),
                  Optional.of(id),
                  parentToolCallId,
                  parentToolName));
        } else {
          String callId = extractCallId(record, index + 1);
          frames.add(
              new AssistantCallFrame(
                  index + 1,
                  record,
                  callId,
                  CallScope.MAIN,
                  Optional.empty(),
                  Optional.empty(),
                  Optional.empty(),
                  Optional.empty()));
        }
      }
      return List.copyOf(frames);
    }

    private static List<String> callIds(List<AssistantCallFrame> frames) {
      return frames.stream().map(AssistantCallFrame::callId).toList();
    }
  }

  /**
   * 表示 ExecutionContext 数据。
   *
   * @param frames assistant 调用帧列表。
   * @param toolResultConsumers tool result 消费者映射。
   * @param toolDeclarations tool declaration 归属映射。
   */
  private record ExecutionContext(
      /* assistant 调用帧列表 */
      @NotNull List<AssistantCallFrame> frames,
      /* tool result 消费者映射 */
      @NotNull Map<String, String> toolResultConsumers,
      /* tool declaration 归属映射 */
      @NotNull Map<String, String> toolDeclarations) {

    private static ExecutionContext create(
        List<? extends SourceRecord> records,
        List<SourceRecord> assistantMessages,
        List<NormalizedCall> calls) {
      List<String> callIds = calls.stream().map(NormalizedCall::callId).toList();
      List<AssistantCallFrame> frames =
          IntStream.range(0, assistantMessages.size())
              .mapToObj(index -> executionFrame(assistantMessages.get(index), index, callIds))
              .toList();
      List<String> consumerCallIds = callIds.isEmpty() ? CallBuildContext.callIds(frames) : callIds;
      return new ExecutionContext(
          frames,
          mapToolResultConsumers(records, consumerCallIds),
          mapToolDeclarations(records, consumerCallIds));
    }

    public ExecutionContext {
      ValidationSupport.validateCanonicalConstructor(
          ExecutionContext.class, frames, toolResultConsumers, toolDeclarations);
      toolResultConsumers = Map.copyOf(toolResultConsumers);
      toolDeclarations = Map.copyOf(toolDeclarations);
    }

    private static AssistantCallFrame executionFrame(
        SourceRecord record, int zeroBasedIndex, List<String> callIds) {
      int callIndex = zeroBasedIndex + 1;
      String callId =
          zeroBasedIndex < callIds.size()
              ? callIds.get(zeroBasedIndex)
              : extractCallId(record, callIndex);
      Optional<String> subagent = displaySubagentId(record);
      Optional<String> parentToolCallId =
          relationValue(record, SourceRecordRelation::parentToolCallId);
      return new AssistantCallFrame(
          callIndex,
          record,
          callId,
          subagent.isPresent() ? CallScope.SUBAGENT : CallScope.MAIN,
          relationValue(record, SourceRecordRelation::parentCallId),
          subagent,
          parentToolCallId,
          relationValue(record, SourceRecordRelation::parentToolName));
    }
  }

  private static Optional<String> relationValue(
      SourceRecord record, Function<SourceRecordRelation, Optional<String>> getter) {
    SourceRecordRelation relation = record.relation();
    return relation == null ? Optional.empty() : getter.apply(relation);
  }
}
