package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.RoundIndexDto;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 将包含 subagent 调用的归一化 round 投影为页面 round row 口径。 */
final class RoundIndexProjection {

  private RoundIndexProjection() {}

  static List<RoundIndexDto> pageDtos(
      SessionDetail detail, SessionDetailParityAnalyzer.Result parity) {
    return pageDtos(detail, null, parity);
  }

  static List<RoundIndexDto> pageDtos(
      SessionDetail detail,
      NormalizedSessionArtifact artifact,
      SessionDetailParityAnalyzer.Result parity) {
    return dtos(
        detail,
        artifact,
        (round, sessionTokens, loadedArtifact) ->
            toPageDto(round, sessionTokens, loadedArtifact, parity.round(round.roundIndex())));
  }

  static List<RoundIndexDto> exportDtos(SessionDetail detail) {
    return exportDtos(detail, null);
  }

  static List<RoundIndexDto> exportDtos(SessionDetail detail, NormalizedSessionArtifact artifact) {
    return dtos(detail, artifact, RoundIndexProjection::toExportDto);
  }

  private static List<RoundIndexDto> dtos(
      SessionDetail detail, NormalizedSessionArtifact artifact, RoundDtoFactory factory) {
    long sessionTokens = detail.sessionRow().totalTokens();
    List<RoundIndexDto> rows = new ArrayList<>();
    for (CallRound round : detail.rounds()) {
      rows.add(factory.create(round, sessionTokens, artifact));
    }
    return List.copyOf(rows);
  }

  static Projection project(CallRound round, NormalizedSessionArtifact artifact) {
    if (artifact == null) {
      return Projection.fromRound(round, false);
    }
    List<NormalizedCall> roundCalls = callsForRound(round, artifact);
    if (roundCalls.isEmpty()) {
      return Projection.fromRound(round, false);
    }
    boolean hasSubagent = containsSubagentCall(roundCalls);
    List<NormalizedCall> displayCalls = displayCalls(roundCalls);
    return Projection.fromCalls(displayCalls, toolIdsFor(artifact, displayCalls), hasSubagent);
  }

  private static RoundIndexDto toPageDto(
      CallRound round,
      long sessionTokens,
      NormalizedSessionArtifact artifact,
      SessionDetailParityAnalyzer.RoundParity parity) {
    Map<String, Object> parityMap = parity.toMap();
    List<String> failedToolIds =
        displayedFailures(
            round,
            artifact,
            parity.failedToolIds.isEmpty() ? round.failedToolCallIds() : parity.failedToolIds);
    List<String> signals =
        parity.signals.isEmpty()
            ? failedSignals(failedToolIds.size())
            : List.copyOf(parity.signals);
    boolean failed = !failedToolIds.isEmpty() || Boolean.TRUE.equals(parityMap.get("hasIssues"));
    return toDto(round, sessionTokens, artifact, failedToolIds, failed, signals, parityMap);
  }

  private static RoundIndexDto toExportDto(
      CallRound round, long sessionTokens, NormalizedSessionArtifact artifact) {
    List<String> failures = displayedFailures(round, artifact, round.failedToolCallIds());
    return toDto(
        round,
        sessionTokens,
        artifact,
        failures,
        !failures.isEmpty(),
        failedSignals(failures.size()),
        Map.of());
  }

  private static List<String> displayedFailures(
      CallRound round, NormalizedSessionArtifact artifact, List<String> failures) {
    if (artifact == null) return List.copyOf(failures);
    List<String> visibleIds = project(round, artifact).toolCallIds();
    return failures.stream().filter(visibleIds::contains).distinct().toList();
  }

  private static List<NormalizedCall> callsForRound(
      CallRound round, NormalizedSessionArtifact artifact) {
    Set<String> roundCallIds = new LinkedHashSet<>(round.calls());
    List<NormalizedCall> matches = new ArrayList<>();
    for (NormalizedCall call : artifact.calls()) {
      if (roundCallIds.contains(call.callId())) {
        matches.add(call);
      }
    }
    return List.copyOf(matches);
  }

  private static boolean containsSubagentCall(List<NormalizedCall> calls) {
    for (NormalizedCall call : calls) {
      if (call.scope() == CallScope.SUBAGENT) {
        return true;
      }
    }
    return false;
  }

  private static List<NormalizedCall> displayCalls(List<NormalizedCall> roundCalls) {
    List<NormalizedCall> mainCalls = new ArrayList<>();
    for (NormalizedCall call : roundCalls) {
      if (call.scope() == CallScope.MAIN) {
        mainCalls.add(call);
      }
    }
    return mainCalls.isEmpty() ? List.copyOf(roundCalls) : List.copyOf(mainCalls);
  }

  private static List<String> toolIdsFor(
      NormalizedSessionArtifact artifact, List<NormalizedCall> displayCalls) {
    // 仅统计当前展示调用实际声明的工具执行，不计请求消费的历史结果。
    LinkedHashSet<String> toolIds = collectExecutionToolIds(artifact, displayCalls);
    if (!toolIds.isEmpty()) {
      return List.copyOf(toolIds);
    }
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Fallback: response toolCallIds only — never requestToolResultIds`
    LinkedHashSet<String> responseToolIds = new LinkedHashSet<>();
    for (NormalizedCall call : displayCalls) {
      responseToolIds.addAll(call.response().toolCallIds());
    }
    return List.copyOf(responseToolIds);
  }

  private static LinkedHashSet<String> collectExecutionToolIds(
      NormalizedSessionArtifact artifact, List<NormalizedCall> displayCalls) {
    Set<String> displayCallIds = new LinkedHashSet<>();
    for (NormalizedCall call : displayCalls) {
      displayCallIds.add(call.callId());
    }
    LinkedHashSet<String> toolIds = new LinkedHashSet<>();
    for (NormalizedToolExecution exec : artifact.toolExecutions()) {
      if (displayCallIds.contains(exec.declaredByCallId())) {
        toolIds.add(exec.toolCallId());
      }
    }
    return toolIds;
  }

  private static RoundIndexDto toDto(
      CallRound round,
      long sessionTokens,
      NormalizedSessionArtifact artifact,
      List<String> failedToolIds,
      boolean failed,
      List<String> signals,
      Map<String, Object> parity) {
    Projection projection = project(round, artifact);
    Map<String, Object> displayParity = new LinkedHashMap<>(parity);
    String toolSummary = toolCountSummary(projection.toolCallIds(), artifact);
    if (!toolSummary.isBlank()) {
      displayParity.put("summary", toolSummary);
    }
    List<String> safeFailedToolIds = safeList(failedToolIds);
    return new RoundIndexDto(
        round.roundIndex(),
        projection.callIds(),
        projection.toolCallIds(),
        round.parentCallId(),
        TokenSegments.of(
            projection.freshInputTokens(),
            projection.cacheReadTokens(),
            projection.cacheWriteTokens(),
            projection.outputTokens()),
        projection.callIds().size(),
        projection.toolCallIds().size(),
        safeFailedToolIds.size(),
        safeFailedToolIds,
        tokenShare(sessionTokens, projection.totalTokens()),
        failed ? "failed" : "ok",
        mergedSignals(signals, safeFailedToolIds, projection.hasSubagent()),
        displayParity);
  }

  /** 汇总与详情共用工具 ID 集合；参数只在工具明细展示。 */
  static String toolCountSummary(List<String> toolIds, NormalizedSessionArtifact artifact) {
    if (artifact == null || toolIds.isEmpty()) {
      return "";
    }
    Set<String> remaining = new LinkedHashSet<>(toolIds);
    Map<String, Integer> counts = new LinkedHashMap<>();
    for (NormalizedToolExecution tool : artifact.toolExecutions()) {
      if (remaining.remove(tool.toolCallId())) {
        counts.merge(tool.name(), 1, Integer::sum);
      }
    }
    return String.join(
        " · ", counts.entrySet().stream().map(e -> e.getKey() + " × " + e.getValue()).toList());
  }

  private static List<String> safeList(List<String> values) {
    return values == null ? List.of() : List.copyOf(values);
  }

  private static Double tokenShare(long sessionTokens, long roundTokens) {
    return sessionTokens > 0 ? roundTokens / (double) sessionTokens : null;
  }

  private static List<String> failedSignals(long failedToolCount) {
    return failedToolCount > 0 ? List.of("Failed") : List.of();
  }

  private static List<String> mergedSignals(
      List<String> signals, List<String> failedToolIds, boolean hasSubagent) {
    LinkedHashSet<String> signalSet = new LinkedHashSet<>(safeList(signals));
    if (!failedToolIds.isEmpty() && signalSet.isEmpty()) {
      signalSet.add("Failed");
    }
    if (hasSubagent) {
      signalSet.add("Subagent");
    }
    return List.copyOf(signalSet);
  }

  /** 创建 round index DTO 的内部工厂。 */
  @FunctionalInterface
  private interface RoundDtoFactory {
    RoundIndexDto create(CallRound round, long sessionTokens, NormalizedSessionArtifact artifact);
  }

  /**
   * 表示 round row 的展示口径。
   *
   * @param callIds 展示口径下的 call ID 列表。
   * @param toolCallIds 展示口径下的 tool call ID 列表。
   * @param freshInputTokens 主 agent 或回退口径 fresh input token 数。
   * @param cacheReadTokens 主 agent 或回退口径 cache read token 数。
   * @param cacheWriteTokens 主 agent 或回退口径 cache write token 数。
   * @param outputTokens 主 agent 或回退口径 output token 数。
   * @param totalTokens 主 agent 或回退口径 total token 数。
   * @param hasSubagent 是否包含 subagent child calls。
   */
  record Projection(
      List<String> callIds,
      List<String> toolCallIds,
      long freshInputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      long outputTokens,
      long totalTokens,
      boolean hasSubagent) {

    private static Projection fromRound(CallRound round, boolean hasSubagent) {
      return new Projection(
          round.calls(),
          round.toolCallIds(),
          round.freshInputTokens(),
          round.cacheReadTokens(),
          round.cacheWriteTokens(),
          round.outputTokens(),
          round.totalTokens(),
          hasSubagent);
    }

    private static Projection fromCalls(
        List<NormalizedCall> calls, List<String> toolCallIds, boolean hasSubagent) {
      List<String> callIds = calls.stream().map(NormalizedCall::callId).toList();
      long fresh = 0;
      long cacheRead = 0;
      long cacheWrite = 0;
      long output = 0;
      long total = 0;
      for (NormalizedCall call : calls) {
        NormalizedCallUsage usage = call.usage();
        fresh += usage.fresh();
        cacheRead += usage.cacheRead();
        cacheWrite += usage.cacheWrite();
        output += usage.output();
        total += usage.total();
      }
      return new Projection(
          callIds, toolCallIds, fresh, cacheRead, cacheWrite, output, total, hasSubagent);
    }
  }
}
