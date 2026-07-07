package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.sqlite.NormalizedArtifactLoader;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.RoundIndexDto;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/** 将包含 subagent 调用的归一化 round 投影为页面 round row 口径。 */
final class RoundIndexProjection {

  private RoundIndexProjection() {}

  static Optional<NormalizedSessionArtifact> loadArtifact(SessionDetail detail) {
    if (detail == null || !detail.hasArtifact()) {
      return Optional.empty();
    }
    try {
      return Optional.of(NormalizedArtifactLoader.load(Path.of(detail.artifactPath())));
    } catch (IOException | RuntimeException ignored) {
      return Optional.empty();
    }
  }

  static List<RoundIndexDto> pageDtos(
      SessionDetail detail, SessionDetailParityAnalyzer.Result parity) {
    return dtos(
        detail,
        (round, sessionTokens, artifact) ->
            toPageDto(round, sessionTokens, artifact, parity.round(round.roundIndex())));
  }

  static List<RoundIndexDto> exportDtos(SessionDetail detail) {
    return dtos(detail, RoundIndexProjection::toExportDto);
  }

  private static List<RoundIndexDto> dtos(SessionDetail detail, RoundDtoFactory factory) {
    NormalizedSessionArtifact artifact = loadArtifact(detail).orElse(null);
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
    return Projection.fromCalls(
        displayCalls, toolIdsFor(round, artifact, displayCalls), hasSubagent);
  }

  private static RoundIndexDto toPageDto(
      CallRound round,
      long sessionTokens,
      NormalizedSessionArtifact artifact,
      SessionDetailParityAnalyzer.RoundParity parity) {
    Map<String, Object> parityMap = parity.toMap();
    List<String> failedToolIds =
        parity.failedToolIds.isEmpty()
            ? round.failedToolCallIds()
            : List.copyOf(parity.failedToolIds);
    List<String> signals =
        parity.signals.isEmpty()
            ? failedSignals(round.failedToolCount())
            : List.copyOf(parity.signals);
    boolean failed = !failedToolIds.isEmpty() || Boolean.TRUE.equals(parityMap.get("hasIssues"));
    return toDto(round, sessionTokens, artifact, failedToolIds, failed, signals, parityMap);
  }

  private static RoundIndexDto toExportDto(
      CallRound round, long sessionTokens, NormalizedSessionArtifact artifact) {
    return toDto(
        round,
        sessionTokens,
        artifact,
        round.failedToolCallIds(),
        round.failedToolCount() > 0,
        failedSignals(round.failedToolCount()),
        Map.of());
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
      CallRound round, NormalizedSessionArtifact artifact, List<NormalizedCall> displayCalls) {
    LinkedHashSet<String> toolIds =
        displayCalls.stream()
            .flatMap(RoundIndexProjection::callToolIdStream)
            .collect(Collectors.toCollection(LinkedHashSet::new));
    if (shouldUseRoundToolFallback(toolIds, displayCalls)) {
      return List.copyOf(round.toolCallIds());
    }
    addDeclaredToolIds(artifact, displayCalls, toolIds);
    return List.copyOf(toolIds);
  }

  private static Stream<String> callToolIdStream(NormalizedCall call) {
    return Stream.concat(
        call.response().toolCallIds().stream(), call.request().toolResultIds().stream());
  }

  private static boolean shouldUseRoundToolFallback(
      LinkedHashSet<String> toolIds, List<NormalizedCall> displayCalls) {
    return toolIds.isEmpty() && !hasMainCall(displayCalls);
  }

  private static boolean hasMainCall(List<NormalizedCall> calls) {
    for (NormalizedCall call : calls) {
      if (call.scope() == CallScope.MAIN) {
        return true;
      }
    }
    return false;
  }

  private static void addDeclaredToolIds(
      NormalizedSessionArtifact artifact,
      List<NormalizedCall> displayCalls,
      LinkedHashSet<String> toolIds) {
    Set<String> declaredByDisplay = new LinkedHashSet<>();
    for (NormalizedCall call : displayCalls) {
      declaredByDisplay.add(call.callId());
    }
    for (NormalizedToolExecution exec : artifact.toolExecutions()) {
      if (declaredByDisplay.contains(exec.declaredByCallId())) {
        toolIds.add(exec.toolCallId());
      }
    }
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
        parity);
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
