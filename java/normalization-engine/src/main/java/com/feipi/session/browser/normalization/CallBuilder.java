package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
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
    return context.frames().stream()
        .map(frame -> buildCall(context, classified.toolResults(), frame))
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
    return Stream.concat(
            assistantToolExecutions(context).stream(),
            standaloneToolExecutions(classified.toolUses(), calls, context.toolResultConsumers())
                .stream())
        .toList();
  }

  private static NormalizedCall buildCall(
      CallBuildContext context, List<SourceRecord> toolResults, AssistantCallFrame frame) {
    SourceRecord record = frame.record();
    NormalizedCallUsage usage = TokenAccountant.extractUsage(record);

    return new NormalizedCall(
        frame.callId(),
        frame.index(),
        "C" + frame.index(),
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        record.turnId(),
        record.model().orElse(""),
        record.timestamp(),
        usage,
        new NormalizedCallRequest(
            toolResultIdsForCall(toolResults, context.toolResultConsumers(), frame.callId())),
        new NormalizedCallResponse(
            record.toolCalls().stream().map(SourceToolCall::toolCallId).toList()),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
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

  private static List<NormalizedToolExecution> assistantToolExecutions(ExecutionContext context) {
    return context.frames().stream()
        .flatMap(frame -> assistantToolExecutions(context.toolResultConsumers(), frame))
        .toList();
  }

  private static Stream<NormalizedToolExecution> assistantToolExecutions(
      Map<String, String> consumers, AssistantCallFrame frame) {
    return frame.record().toolCalls().stream()
        .map(
            toolCall ->
                toolExecution(
                    toolCall.toolCallId(),
                    toolCall.name(),
                    frame.callId(),
                    Optional.ofNullable(consumers.get(toolCall.toolCallId()))));
  }

  private static List<NormalizedToolExecution> standaloneToolExecutions(
      List<SourceRecord> toolUses, List<NormalizedCall> calls, Map<String, String> consumers) {
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
              declaredByLastCall(calls),
              Optional.ofNullable(consumers.get(toolCallId.get()))));
    }
    return executions;
  }

  private static NormalizedToolExecution toolExecution(
      String toolCallId, String name, String declaredByCallId, Optional<String> consumedByCallId) {
    return new NormalizedToolExecution(
        toolCallId,
        name,
        CallScope.MAIN,
        declaredByCallId,
        consumedByCallId,
        Optional.empty(),
        Optional.empty(),
        0L,
        List.of(),
        Optional.empty());
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

  private static String extractCallId(SourceRecord record, int fallbackIndex) {
    return record.callId().orElse("C" + fallbackIndex);
  }

  /** 单个 assistant 调用在归一化过程中的稳定帧。 */
  private record AssistantCallFrame(int index, SourceRecord record, String callId) {}

  /** 构建 {@link NormalizedCall} 时使用的共享上下文。 */
  private record CallBuildContext(
      List<AssistantCallFrame> frames, Map<String, String> toolResultConsumers) {

    private static CallBuildContext create(
        List<? extends SourceRecord> records, List<SourceRecord> assistantMessages) {
      List<AssistantCallFrame> frames =
          IntStream.range(0, assistantMessages.size())
              .mapToObj(
                  index -> {
                    SourceRecord record = assistantMessages.get(index);
                    return new AssistantCallFrame(
                        index + 1, record, extractCallId(record, index + 1));
                  })
              .toList();
      return new CallBuildContext(frames, mapToolResultConsumers(records, callIds(frames)));
    }

    private static List<String> callIds(List<AssistantCallFrame> frames) {
      return frames.stream().map(AssistantCallFrame::callId).toList();
    }
  }

  /** 构建 {@link NormalizedToolExecution} 时使用的共享上下文。 */
  private record ExecutionContext(
      List<AssistantCallFrame> frames, Map<String, String> toolResultConsumers) {

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
      return new ExecutionContext(frames, mapToolResultConsumers(records, consumerCallIds));
    }

    private static AssistantCallFrame executionFrame(
        SourceRecord record, int zeroBasedIndex, List<String> callIds) {
      int callIndex = zeroBasedIndex + 1;
      String callId =
          zeroBasedIndex < callIds.size()
              ? callIds.get(zeroBasedIndex)
              : extractCallId(record, callIndex);
      return new AssistantCallFrame(callIndex, record, callId);
    }
  }
}
