package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * RoundIndexProjection 回归测试。
 *
 * <p>验证 toolCallIds 只计实际 NormalizedToolExecution（按 declaredByCallId，去重）， 不把 requestToolResultIds
 * 当执行。
 */
@DisplayName("RoundIndexProjection")
class RoundIndexProjectionTest {

  @Test
  void canonicalCountsOverrideRawFragmentsAndRemainZeroWhenEmpty(
      @org.junit.jupiter.api.io.TempDir Path directory) throws Exception {
    Path source = directory.resolve("synthetic-fragments.jsonl");
    String fragment =
        """
        {"type":"assistant","message":{"id":"same-response","usage":{"output_tokens":2},"content":"fragment"}}
        """;
    Files.writeString(source, fragment + fragment);
    var row =
        new SessionRow(
            "qoder:synthetic-counts",
            "qoder",
            "synthetic-counts",
            "synthetic",
            "",
            "",
            "",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:00:01Z",
            1,
            0,
            0,
            "synthetic-model",
            "",
            "fixture",
            0,
            2,
            0,
            4,
            0,
            0,
            0,
            4,
            0,
            0,
            0,
            0,
            source.toString());
    var oneCall = buildCall("logical-response", 1, List.of(), List.of());
    for (var artifact :
        List.of(buildArtifact(List.of(oneCall), List.of()), buildArtifact(List.of(), List.of()))) {
      var detail =
          new SessionDetail(
              row,
              SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()),
              List.of(),
              PayloadVisibility.STANDARD,
              "",
              "",
              "cache");
      var result = SessionDetailParityAnalyzer.analyze(detail, artifact);
      long expected = artifact.calls().size();
      assertThat(result.metrics)
          .containsEntry("mainCalls", expected)
          .containsEntry("workloadCalls", expected)
          .containsEntry("subagentCalls", 0L);
      var agents = (List<?>) result.diagnostics.get("agents");
      assertThat(((Map<?, ?>) agents.get(0)).get("llmCalls")).isEqualTo(expected);
      assertThat(SessionDetailParityAnalyzer.analyze(detail).metrics)
          .containsEntry("mainCalls", 2L);
    }
  }

  @Test
  void plainTextSummaryPrefersVisibleUserAndInternalContextIsNotUserInput() {
    for (String user :
        List.of("please inspect", "<codex_internal_context>continue</codex_internal_context>")) {
      var call =
          new NormalizedCall(
              "c1",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "fixture-model",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(
                  Map.of("role", "user", "type", "text", "text", user),
                  Map.of("role", "assistant", "type", "text", "text", "completed inspection")),
              Map.of(),
              Map.of());
      var content =
          RoundContentProjection.from(
              new CallRound(1, List.of("c1"), List.of(), ""),
              buildArtifact(List.of(call), List.of()));
      assertThat(content.summary())
          .isEqualTo(user.equals("please inspect") ? user : "completed inspection");
      assertThat(content.userInput()).isEqualTo(user.equals("please inspect"));
    }
  }

  @Test
  void contentUsesCallIdentityEvenWhenRoundAndRecordPositionsDiffer() {
    var first = contentCall("first", 1, "2026-07-06T02:00:00Z", "first response", List.of());
    var fragment = contentCall("fragment", 2, "2026-07-06T02:00:01Z", "first fragment", List.of());
    var second =
        contentCall("second", 3, "2026-07-06T02:03:00Z", "second response", List.of("prior-tool"));
    var artifact = buildArtifact(List.of(first, fragment, second), List.of());
    var round = new CallRound(2, List.of("second"), List.of("prior-tool"), "");

    var content = RoundContentProjection.from(round, artifact);
    assertThat(content.summary()).isEqualTo("second response");
    assertThat(content.time()).isEqualTo("10:03:00");
    assertThat(content.userInput()).isFalse();
  }

  @Test
  void absentRoundIdentityNeverBorrowsAnotherCallsContentOrTime() {
    var artifact =
        buildArtifact(
            List.of(contentCall("other", 1, "2026-07-06T02:00:00Z", "unrelated", List.of())),
            List.of());
    var content =
        RoundContentProjection.from(new CallRound(1, List.of("missing"), List.of(), ""), artifact);
    assertThat(content.summary()).isEqualTo("内容未记录");
    assertThat(content.time()).isEmpty();
  }

  private static NormalizedCall contentCall(
      String id, int index, String time, String text, List<String> results) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "fixture-model",
        Optional.of(time),
        NormalizedCallUsage.empty(),
        new NormalizedCallRequest(results),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(
            Map.of("role", "assistant", "type", "text", "text", text),
            Map.of("role", "user", "type", "tool_result", "text", "not a user message")),
        Map.of(),
        Map.of());
  }

  @Test
  void summaryCountsDistinctToolsWithoutListingTheirInputsOrOtherRounds() {
    var first = namedExec("read-1", "Read");
    var artifact =
        buildArtifact(
            List.of(),
            List.of(
                first,
                first,
                namedExec("read-2", "Read"),
                namedExec("grep-1", "Grep"),
                namedExec("other-round", "Write")));

    assertThat(
            RoundIndexProjection.toolCountSummary(
                List.of("read-1", "read-2", "grep-1", "read-1"), artifact))
        .isEqualTo("Read × 2 · Grep × 1");
    assertThat(RoundIndexProjection.toolCountSummary(List.of(), artifact)).isEmpty();
    assertThat(RoundIndexProjection.toolCountSummary(List.of("read-1"), null)).isEmpty();
  }

  @Test
  void requestResultsNeverBecomeExecutionsWhenResponseDeclaresNoTools() {
    var call = buildCall("call-1", 1, List.of("prior-tool"), List.of());
    var round = new CallRound(1, List.of("call-1"), List.of("prior-tool"), "");
    var artifact = buildArtifact(List.of(call), List.of());

    assertThat(RoundIndexProjection.project(round, artifact).toolCallIds()).isEmpty();
  }

  private static NormalizedToolExecution namedExec(String id, String name) {
    return new NormalizedToolExecution(
        id,
        name,
        CallScope.MAIN,
        "call-1",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        0,
        List.of("/synthetic/should-not-appear-in-summary"),
        Optional.empty());
  }

  @Test
  @DisplayName("5 calls / 4 executions 投影只计实际 execution，不含 requestToolResultIds")
  void projectionCountsOnlyActualExecutions() {
    // 构造五条调用：首条消费历史工具结果，但没有对应的工具执行记录。
    NormalizedCall call1 = buildCall("call-1", 1, List.of("tool-orphan"), List.of("tool-resp-1"));
    NormalizedCall call2 = buildCall("call-2", 2, List.of(), List.of("tool-resp-2"));
    NormalizedCall call3 = buildCall("call-3", 3, List.of(), List.of("tool-resp-3"));
    NormalizedCall call4 = buildCall("call-4", 4, List.of(), List.of("tool-resp-4"));
    NormalizedCall call5 = buildCall("call-5", 5, List.of(), List.of());

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Only 4 actual executions declared by call-2..call-5`
    NormalizedToolExecution exec1 = buildExec("tool-resp-2", "call-2");
    NormalizedToolExecution exec2 = buildExec("tool-resp-3", "call-3");
    NormalizedToolExecution exec3 = buildExec("tool-resp-4", "call-4");
    NormalizedToolExecution exec4 = buildExec("tool-extra", "call-5");

    NormalizedSessionArtifact artifact =
        buildArtifact(
            List.of(call1, call2, call3, call4, call5), List.of(exec1, exec2, exec3, exec4));

    CallRound round =
        new CallRound(
            1,
            List.of("call-1", "call-2", "call-3", "call-4", "call-5"),
            List.of("tool-orphan", "tool-resp-1", "tool-resp-2", "tool-resp-3", "tool-resp-4"),
            "",
            100,
            50,
            0,
            30,
            180);

    RoundIndexProjection.Projection projection = RoundIndexProjection.project(round, artifact);

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`toolCallIds should only contain actual executions`
    assertThat(projection.toolCallIds())
        .containsExactlyInAnyOrder("tool-resp-2", "tool-resp-3", "tool-resp-4", "tool-extra");
    assertThat(projection.toolCallIds()).doesNotContain("tool-orphan", "tool-resp-1");
    assertThat(projection.callIds())
        .containsExactly("call-1", "call-2", "call-3", "call-4", "call-5");
  }

  @Test
  @DisplayName("无 execution 时回退到 response toolCallIds")
  void projectionFallsBackToResponseToolCallIdsWhenNoExecutions() {
    NormalizedCall call1 = buildCall("call-1", 1, List.of("tool-result-1"), List.of("tool-resp-1"));

    NormalizedSessionArtifact artifact = buildArtifact(List.of(call1), List.of());

    CallRound round =
        new CallRound(1, List.of("call-1"), List.of("tool-resp-1"), "", 50, 0, 0, 10, 60);

    RoundIndexProjection.Projection projection = RoundIndexProjection.project(round, artifact);

    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`No executions, so fallback to response toolCallIds`
    assertThat(projection.toolCallIds()).containsExactly("tool-resp-1");
    assertThat(projection.toolCallIds()).doesNotContain("tool-result-1");
  }

  private static NormalizedCall buildCall(
      String callId,
      int index,
      List<String> requestToolResultIds,
      List<String> responseToolCallIds) {
    return new NormalizedCall(
        callId,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "test-model",
        Optional.empty(),
        new NormalizedCallUsage(10, 5, 0, 5, 20),
        new NormalizedCallRequest(requestToolResultIds),
        new NormalizedCallResponse(responseToolCallIds),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedToolExecution buildExec(String toolCallId, String declaredByCallId) {
    return new NormalizedToolExecution(
        toolCallId,
        "test-tool",
        CallScope.MAIN,
        declaredByCallId,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        100,
        List.of(),
        Optional.empty());
  }

  private static NormalizedSessionArtifact buildArtifact(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.QODER,
        List.of(
            new NormalizedSourceFile(
                SourceFileRole.TRANSCRIPT,
                Path.of("test.jsonl"),
                Optional.empty(),
                Optional.empty())),
        new NormalizedSessionMetadata(Map.of()),
        calls,
        toolExecutions,
        List.of(),
        Map.of(),
        Map.of());
  }
}
