package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 冻结制品中的主/子工具状态与载荷引用是详情指标的权威。 */
class SessionDetailParityMetricsTest {

  @TempDir Path directory;

  @Test
  void artifactFailuresIncludeChildrenForEveryProviderWithoutInventingPayloadGaps()
      throws Exception {
    Path raw = directory.resolve("current-source.jsonl");
    Files.writeString(
        raw,
        """
        {"type":"response_item","payload":{"type":"function_call","call_id":"later","name":"foreign"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"later","output":"ok"}}
        """);
    for (NormalizedAgent agent : NormalizedAgent.values()) {
      var artifact = completeArtifact(agent);
      var detail = detail(agent, "synthetic", raw, artifact, 99, 0);
      var result = SessionDetailParityAnalyzer.analyze(detail, artifact);

      assertThat(result.metrics)
          .containsEntry("toolCalls", 3L)
          .containsEntry("failedTools", 2L)
          .containsEntry("mainCalls", 1L)
          .containsEntry("subagentCalls", 1L)
          .containsEntry("workloadCalls", 2L)
          .containsEntry("subagentRuns", 1L)
          .containsEntry("payloadGaps", 0L)
          .containsEntry("issueRounds", 1);
      assertThat(result.round(1).failedToolIds).containsExactly("main-failed");
      assertThat(result.round(1).signals).contains("Failed").doesNotContain("Payload Gap");
      assertThat(result.round(1).payloadGap).isFalse();
      assertThat(result.diagnostics.toString()).doesNotContain("foreign", "later");
      var agents = (List<?>) result.diagnostics.get("agents");
      assertThat(((Map<?, ?>) agents.get(0)).get("failures")).isEqualTo(1L);
      assertThat(((Map<?, ?>) agents.get(1)).get("failures")).isEqualTo(1L);
      var impact = (Map<?, ?>) result.diagnostics.get("toolImpact");
      assertThat(impact.get("failedTools")).isEqualTo(2L);
      assertThat(impact.get("distinctTools")).isEqualTo(1);
    }
  }

  @Test
  void metricsApiUsesTheSameCanonicalToolFailuresAtBothLevels() {
    var artifact = completeArtifact(NormalizedAgent.CLAUDE_CODE);
    var detail = detail(NormalizedAgent.CLAUDE_CODE, "api-fixture", null, artifact, 99, 0);
    var handler =
        new SessionDetailApiHandler(
            ctx ->
                new SessionDetailApiHandler.LoadedDetail(
                    new SessionDetailApiResponses.SessionDetailFilterEcho(
                        "claude_code", "api-fixture", "standard", "", ""),
                    new SessionDetailUseCase.AnnotatedDetailContext(
                        detail,
                        SessionAnomalySummary.empty(detail.sessionRow().sessionKey()),
                        artifact),
                    "/synthetic",
                    false));
    JavalinTest.test(
        Javalin.create(config -> config.routes.get("/metrics", handler::handleMetrics)),
        (app, client) -> {
          var response = client.get("/metrics");
          assertThat(response.code()).isEqualTo(200);
          var body = new ObjectMapper().readTree(response.body().string());
          assertThat(body.path("toolCalls").asLong()).isEqualTo(3);
          assertThat(body.path("failedTools").asLong()).isEqualTo(2);
          assertThat(body.at("/parity/failedTools").asLong()).isEqualTo(2);
          assertThat(body.at("/parity/payloadGaps").asLong()).isZero();
        });
  }

  @Test
  void childFailureIsNotReportedAsAMainToolFailure() {
    var artifact =
        artifact(
            NormalizedAgent.QODER,
            List.of(
                call("main", 1, CallScope.MAIN, List.of()),
                call("child", 2, CallScope.SUBAGENT, List.of())),
            List.of(
                tool(
                    "child-failed",
                    "child",
                    CallScope.SUBAGENT,
                    Optional.of("is_error"),
                    Optional.empty())));
    var detail = detail(NormalizedAgent.QODER, "child-only", null, artifact, 1, 1);
    var result = SessionDetailParityAnalyzer.analyze(detail, artifact, false);
    assertThat(result.metrics).containsEntry("failedTools", 1L).containsEntry("issueRounds", 1);
    assertThat(result.round(1).failedToolIds).isEmpty();
    assertThat(result.round(1).signals).contains("Subagent failed").doesNotContain("Failed");
    // 当前展示 MAIN 的状态仍为ok；workload级issueRounds/诊断保留child失败。
    assertThat(result.round(1).hasIssues()).isFalse();
  }

  @Test
  void onlyDanglingPayloadReferencesCreateGapsNotFailureOrUnconsumedResults() {
    var missing =
        new SourceUnitRefRange(
            Optional.empty(), 0, 0, List.of("missing-result"), Optional.of("user"));
    var sequence =
        new SourceUnitRefRange(
            Optional.of("missing-sequence"), 0, Integer.MAX_VALUE, List.of(), Optional.empty());
    var artifact =
        artifact(
            NormalizedAgent.CODEX,
            List.of(call("main", 1, CallScope.MAIN, List.of(missing, missing, sequence))),
            List.of(tool("success", "main", CallScope.MAIN, Optional.empty(), Optional.empty())));
    var detail = detail(NormalizedAgent.CODEX, "missing-ref", null, artifact, 1, 0);
    var result = SessionDetailParityAnalyzer.analyze(detail, artifact, false);
    assertThat(result.metrics)
        .containsEntry("failedTools", 0L)
        .containsEntry("payloadGaps", 2L)
        .containsEntry("issueRounds", 1);
    assertThat(result.round(1).signals).containsExactly("Payload Gap");
    assertThat(result.round(1).payloadGap).isTrue();
    assertThat(result.diagnostics.get("issueCount")).isEqualTo(2);
  }

  @Test
  void referencedToolResultMustExistButAnExplicitEmptyResultIsNotAGap() {
    var consumer =
        new NormalizedCall(
            "consumer",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            new NormalizedCallRequest(
                List.of("missing", "empty-inline", "empty-catalog", "empty-codex")),
            NormalizedCallResponse.empty(),
            List.of(),
            List.of(
                Map.of("type", "tool_result", "tool_call_id", "empty-inline", "content", ""),
                Map.of(
                    "content",
                    List.of(
                        Map.of(
                            "type",
                            "function_call_output",
                            "call_id",
                            "empty-codex",
                            "output",
                            "")))),
            Map.of(),
            Map.of());
    var catalogEntry =
        new SourceUnitCatalogEntry(
            "empty-unit",
            "/synthetic/source",
            "fixture:1",
            "tool_result",
            "tool_results",
            SourceUnitDirection.REQUEST,
            0,
            0,
            ByteRange.empty(),
            "synthetic-hash",
            Optional.empty(),
            Optional.of("empty-catalog"),
            0,
            Optional.empty(),
            Optional.of(""),
            "",
            Optional.empty(),
            Optional.empty(),
            List.of());
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            List.of(consumer),
            List.of(),
            List.of(),
            Map.of("empty-unit", catalogEntry),
            Map.of());
    var detail = detail(NormalizedAgent.CODEX, "referenced-result", null, artifact, 0, 0);
    var result = SessionDetailParityAnalyzer.analyze(detail, artifact, false);
    assertThat(result.metrics).containsEntry("failedTools", 0L).containsEntry("payloadGaps", 1L);
    assertThat(result.round(1).signals).containsExactly("Payload Gap");
    var issues = (List<?>) result.diagnostics.get("issues");
    assertThat(issues).hasSize(1);
    assertThat(((Map<?, ?>) issues.get(0)).get("seed"))
        .isEqualTo("referenced-result + consumer + tool-result:missing");
  }

  @Test
  void rowFallbackNeverOverwritesFrozenFailuresWithRawFormatGuesses() throws Exception {
    Path raw = directory.resolve("native-errors.jsonl");
    Files.writeString(
        raw,
        """
        {"type":"assistant","message":{"content":[{"type":"tool_use","id":"raw","name":"Read","input":{}}]}}
        {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"raw","is_error":true,"content":"denied"}]}}
        """);
    for (NormalizedAgent agent : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.QODER)) {
      var detail = detail(agent, "row-fallback", raw, null, 5, 4);
      var result = SessionDetailParityAnalyzer.analyze(detail);
      assertThat(result.metrics)
          .containsEntry("toolCalls", 5L)
          .containsEntry("failedTools", 4L)
          .containsEntry("payloadGaps", 0L);
      var agents = (List<?>) result.diagnostics.get("agents");
      assertThat(((Map<?, ?>) agents.get(0)).get("failures")).isEqualTo(1L);
    }
  }

  @Test
  void sessionIdentityNeverPadsIssuesOrPayloadGaps() {
    // 旧实现针对某个历史身份和48失败添加了额外的gap/round；任意身份必须同口径。
    for (String sessionId : List.of("synthetic-reference", "synthetic-other-session")) {
      var detail = detail(NormalizedAgent.CODEX, sessionId, null, null, 48, 48);
      var result = SessionDetailParityAnalyzer.analyze(detail);
      assertThat(result.metrics)
          .containsEntry("failedTools", 48L)
          .containsEntry("payloadGaps", 0L)
          .containsEntry("issueRounds", 0);
      assertThat(result.diagnostics.get("issueCount")).isEqualTo(0);
    }
  }

  @Test
  void agentUsageAndSharesExcludeToolContextAndDoNotAssignChildrenToMain() {
    var artifact =
        artifact(
            NormalizedAgent.CLAUDE_CODE,
            List.of(
                usageCall("main", 1, "", 4, 3, 1, 2, Map.of(), "large tool output ".repeat(2000)),
                usageCall(
                    "child", 2, "child-agent", 8, 6, 2, 4, Map.of(), "child result ".repeat(1000))),
            List.of(
                tool("main-failed", "main", CallScope.MAIN, Optional.empty(), Optional.empty()),
                tool(
                    "child-failed",
                    "child",
                    CallScope.SUBAGENT,
                    Optional.empty(),
                    Optional.empty())));
    var result = usageDiagnostics(artifact, 12, 9, 3, 6, reported());
    var agents = result.path("agents");
    assertThat(agents.path(0).path("tokens").asText()).isEqualTo("10");
    assertThat(agents.path(1).path("tokens").asText()).isEqualTo("20");
    assertThat(agents.path(0).path("tokenSegments").path("total").asLong()).isEqualTo(10);
    assertThat(agents.path(1).path("tokenSegments").path("total").asLong()).isEqualTo(20);
    assertThat(agents.path(0).path("tokenShare").asText()).isEqualTo("33.3%");
    assertThat(agents.path(1).path("tokenShare").asText()).isEqualTo("66.7%");
    assertThat(agents.path(0).path("tokenShareValue").asDouble()).isEqualTo(100.0 / 3);
    assertThat(agents.path(0).path("tokenShareBasis").asText()).isEqualTo("observed_agent_usage");
    assertThat(agents.path(0).path("tokenShareStatus").asText()).isEqualTo("partial");
    // 会话级已上报标记不能提升逐次调用的未知来源精度。
    assertThat(agents.path(1).at("/tokenSegments/provenance/freshInput").asText())
        .isEqualTo("unknown");
    long composition = 0;
    for (var segment : result.path("contextSegments")) {
      if (segment.path("includedInUsage").asBoolean()) {
        composition += segment.path("tokens").asLong();
      }
      if ("Tool Results".equals(segment.path("label").asText())) {
        assertThat(segment.path("tokens").asLong()).isGreaterThan(30);
        assertThat(segment.path("status").asText()).isEqualTo("estimated");
        assertThat(segment.path("includedInUsage").asBoolean()).isFalse();
        assertThat(segment.path("share").asText()).isEqualTo("unavailable");
      }
    }
    assertThat(composition).isEqualTo(30);
  }

  @Test
  void multipleChildrenKeepOwnFourSegmentsAndSharesUseOnlyObservedUsage() {
    var artifact =
        artifact(
            NormalizedAgent.CODEX,
            List.of(
                usageCall("main", 1, "", 4, 3, 1, 2, reported().toMetadata(), ""),
                usageCall("child", 2, "child-agent", 8, 6, 2, 4, reported().toMetadata(), ""),
                usageCall("child-2", 3, "other-child", 1, 2, 3, 4, Map.of(), "")),
            List.of());
    var agents = usageDiagnostics(artifact, 13, 11, 6, 10, reported()).path("agents");
    assertThat(agents).hasSize(3);
    assertThat(agents.path(0).path("tokenShare").asText()).isEqualTo("25.0%");
    assertThat(agents.path(1).path("subagentId").asText()).isEqualTo("child-agent");
    assertThat(agents.path(1).at("/tokenSegments/fresh").asLong()).isEqualTo(8);
    assertThat(agents.path(1).at("/tokenSegments/cacheRead").asLong()).isEqualTo(6);
    assertThat(agents.path(1).at("/tokenSegments/cacheWrite").asLong()).isEqualTo(2);
    assertThat(agents.path(1).at("/tokenSegments/output").asLong()).isEqualTo(4);
    assertThat(agents.path(1).at("/tokenSegments/provenance/freshInput").asText())
        .isEqualTo("provider_reported");
    assertThat(agents.path(2).at("/tokenSegments/provenance/freshInput").asText())
        .isEqualTo("unknown");
    assertThat(agents.path(2).path("tokenShare").asText()).isEqualTo("25.0%");
    assertThat(agents.path(0).path("tokenShareStatus").asText()).isEqualTo("partial");
  }

  @Test
  void qoderSessionEstimateIsKeptOnlyWhenThereAreNoChildrenToSplit() {
    var estimate =
        new TokenProvenance(
            "estimated", "unavailable", "unavailable", "estimated", "visible_context_v1", 1, 1, 0);
    var main = usageCall("main", 1, "", 0, 0, 0, 0, Map.of(), "");
    var onlyMain = artifact(NormalizedAgent.QODER, List.of(main), List.of());
    var agents = usageDiagnostics(onlyMain, 100, 0, 0, 20, estimate).path("agents");
    assertThat(agents.path(0).path("tokens").asText()).isEqualTo("120");
    assertThat(agents.path(0).at("/tokenSegments/total").asLong()).isEqualTo(120);
    assertThat(agents.path(0).at("/tokenSegments/provenance/freshInput").asText())
        .isEqualTo("estimated");
    assertThat(agents.path(0).path("tokenUsageBasis").asText()).isEqualTo("session_estimate");
    var unlocatedChild = usageDiagnostics(onlyMain, 100, 0, 0, 20, estimate, 1).path("agents");
    assertThat(unlocatedChild.path(0).at("/tokenSegments/total").asLong()).isZero();
    assertThat(unlocatedChild.path(0).path("tokenShareStatus").asText()).isEqualTo("unavailable");
    var withChild =
        artifact(
            NormalizedAgent.QODER,
            List.of(main, usageCall("child", 2, "child-agent", 0, 0, 0, 0, Map.of(), "")),
            List.of());
    var unsplit = usageDiagnostics(withChild, 100, 0, 0, 20, estimate).path("agents");
    for (var agent : unsplit) {
      assertThat(agent.at("/tokenSegments/total").asLong()).isZero();
      assertThat(agent.at("/tokenSegments/provenance/freshInput").asText()).isEqualTo("unknown");
      assertThat(agent.path("tokenShareStatus").asText()).isEqualTo("unavailable");
    }
  }

  @Test
  void actualZeroAndMissingSourceRemainDistinctAndShareHasNoFakeDenominator() {
    var artifact =
        artifact(
            NormalizedAgent.CODEX,
            List.of(
                usageCall("main", 1, "", 0, 0, 0, 0, reported().toMetadata(), ""),
                usageCall("child", 2, "child-agent", 0, 0, 0, 0, Map.of(), "")),
            List.of());
    var agents = usageDiagnostics(artifact, 0, 0, 0, 0, reported()).path("agents");
    assertThat(agents.path(0).at("/tokenSegments/provenance/freshInput").asText())
        .isEqualTo("provider_reported");
    assertThat(agents.path(1).at("/tokenSegments/provenance/freshInput").asText())
        .isEqualTo("unknown");
    for (var agent : agents) {
      assertThat(agent.path("tokens").asText()).isEqualTo("0");
      assertThat(agent.path("tokenShare").asText()).isEqualTo("N/A");
      assertThat(agent.path("tokenShareStatus").asText()).isEqualTo("unavailable");
      assertThat(agent.path("tokenShareValue").isNull()).isTrue();
    }
  }

  @Test
  void completeReportedOwnUsageKeepsMeasuredSharesAndNumericComponents() {
    var artifact =
        artifact(
            NormalizedAgent.CODEX,
            List.of(
                usageCall("main", 1, "", 4, 3, 1, 2, reported().toMetadata(), ""),
                usageCall("child", 2, "child-agent", 8, 6, 2, 4, reported().toMetadata(), "")),
            List.of());
    var agents = usageDiagnostics(artifact, 12, 9, 3, 6, reported()).path("agents");
    assertThat(agents.path(0).path("tokenShareStatus").asText()).isEqualTo("available");
    assertThat(agents.path(1).path("tokenShareStatus").asText()).isEqualTo("available");
    assertThat(agents.path(0).at("/tokenSegments/provenance/unknownSessionCount").asLong())
        .isZero();
    assertThat(agents.path(0).at("/tokenSegments/total").asLong()).isEqualTo(10);
    assertThat(agents.path(1).at("/tokenSegments/total").asLong()).isEqualTo(20);
  }

  @Test
  void shareOfPartialObservedCallsDoesNotUseUnallocatedSessionTokens() {
    var artifact =
        artifact(
            NormalizedAgent.CODEX,
            List.of(
                usageCall("main", 1, "", 4, 3, 1, 2, reported().toMetadata(), ""),
                usageCall("child", 2, "child-agent", 8, 6, 2, 4, reported().toMetadata(), "")),
            List.of());
    var agents = usageDiagnostics(artifact, 82, 9, 3, 6, reported()).path("agents");
    assertThat(agents.path(0).at("/tokenSegments/total").asLong()).isEqualTo(10);
    assertThat(agents.path(1).at("/tokenSegments/total").asLong()).isEqualTo(20);
    assertThat(agents.path(0).path("tokenShare").asText()).isEqualTo("33.3%");
    assertThat(agents.path(1).path("tokenShare").asText()).isEqualTo("66.7%");
    for (var agent : agents) {
      assertThat(agent.path("tokenShareStatus").asText()).isEqualTo("partial");
    }
  }

  @Test
  void callsWithinOneAgentPreserveMixedEvidenceWithoutMultiplyingSessionCoverage() {
    var estimate =
        new TokenProvenance(
            "estimated", "unavailable", "unavailable", "estimated", "visible_context_v1", 1, 1, 0);
    var artifact =
        artifact(
            NormalizedAgent.CLAUDE_CODE,
            List.of(
                usageCall("main", 1, "", 8, 0, 0, 2, estimate.toMetadata(), ""),
                usageCall("next", 2, "", 12, 0, 0, 8, reported().toMetadata(), "")),
            List.of());
    var agent = usageDiagnostics(artifact, 20, 0, 0, 10, reported()).path("agents").path(0);
    assertThat(agent.at("/tokenSegments/total").asLong()).isEqualTo(30);
    assertThat(agent.at("/tokenSegments/provenance/freshInput").asText()).isEqualTo("mixed");
    assertThat(agent.at("/tokenSegments/provenance/estimatedSessionCount").asLong()).isEqualTo(1);
    assertThat(agent.at("/tokenSegments/provenance/unavailableSessionCount").asLong()).isEqualTo(1);
    assertThat(agent.at("/tokenSegments/provenance/unknownSessionCount").asLong()).isZero();
    assertThat(agent.at("/tokenSegments/provenance/estimationMethod").asText())
        .isEqualTo("visible_context_v1");
  }

  private static TokenProvenance reported() {
    return new TokenProvenance(
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "",
        0,
        0,
        0);
  }

  private static NormalizedCall usageCall(
      String id,
      int index,
      String childId,
      long fresh,
      long read,
      long write,
      long output,
      Map<String, Object> source,
      String toolOutput) {
    var scope = childId.isBlank() ? CallScope.MAIN : CallScope.SUBAGENT;
    var base = call(id, index, scope, List.of());
    return new NormalizedCall(
        base.callId(),
        base.callIndex(),
        base.callKey(),
        scope,
        base.parentCallId(),
        base.parentToolCallId(),
        base.turnId(),
        base.model(),
        base.timestamp(),
        new NormalizedCallUsage(fresh, read, write, output, fresh + read + write + output),
        base.request(),
        base.response(),
        List.of(),
        List.of(
            Map.of(
                "role",
                "user",
                "type",
                "tool_result",
                "tool_call_id",
                scope == CallScope.MAIN ? "main-failed" : "child-failed",
                "text",
                toolOutput)),
        Map.of(),
        source,
        childId.isBlank() ? Optional.empty() : Optional.of(childId),
        Optional.empty());
  }

  private static JsonNode usageDiagnostics(
      NormalizedSessionArtifact artifact,
      long fresh,
      long read,
      long write,
      long output,
      TokenProvenance provenance) {
    return usageDiagnostics(artifact, fresh, read, write, output, provenance, 0);
  }

  private static JsonNode usageDiagnostics(
      NormalizedSessionArtifact artifact,
      long fresh,
      long read,
      long write,
      long output,
      TokenProvenance provenance,
      long indexedChildren) {
    var row =
        new SessionRow(
            artifact.agent().getValue() + ":usage",
            artifact.agent().getValue(),
            "usage",
            "Synthetic",
            "",
            "",
            "",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:01Z",
            1,
            0,
            0,
            "synthetic",
            "",
            "fixture",
            0,
            0,
            artifact.toolExecutions().size(),
            output,
            fresh,
            read,
            write,
            fresh + read + write + output,
            0,
            indexedChildren,
            0,
            0,
            "",
            provenance);
    var detail =
        SessionDetailAssembler.assemble(row, artifact, PayloadVisibility.STANDARD, "fixture", 1);
    return new ObjectMapper()
        .valueToTree(SessionDetailParityAnalyzer.analyze(detail, artifact, false).diagnostics);
  }

  private static NormalizedSessionArtifact completeArtifact(NormalizedAgent agent) {
    return artifact(
        agent,
        List.of(
            call("main", 1, CallScope.MAIN, List.of()),
            call("child", 2, CallScope.SUBAGENT, List.of())),
        List.of(
            tool("main-failed", "main", CallScope.MAIN, Optional.of("is_error"), Optional.empty()),
            tool("main-ok", "main", CallScope.MAIN, Optional.empty(), Optional.empty()),
            tool("child-failed", "child", CallScope.SUBAGENT, Optional.empty(), Optional.of(7))));
  }

  private static NormalizedSessionArtifact artifact(
      NormalizedAgent agent, List<NormalizedCall> calls, List<NormalizedToolExecution> tools) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        agent,
        List.of(),
        Map.of(),
        calls,
        tools,
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(
      String id, int index, CallScope scope, List<SourceUnitRefRange> refs) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        scope,
        scope == CallScope.MAIN ? Optional.empty() : Optional.of("main"),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        new NormalizedCallResponse(
            scope == CallScope.MAIN ? List.of("main-failed", "main-ok") : List.of("child-failed")),
        refs,
        List.of(
            Map.of("role", "user", "type", "text", "text", "synthetic request"),
            Map.of("role", "assistant", "type", "text", "text", "synthetic response"),
            Map.of(
                "role",
                "user",
                "type",
                "tool_result",
                "tool_call_id",
                scope == CallScope.MAIN ? "main-failed" : "child-failed",
                "text",
                "complete error payload")),
        Map.of(),
        Map.of(),
        scope == CallScope.MAIN ? Optional.empty() : Optional.of("child-agent"),
        Optional.empty());
  }

  private static NormalizedToolExecution tool(
      String id,
      String callId,
      CallScope scope,
      Optional<String> status,
      Optional<Integer> exitCode) {
    return new NormalizedToolExecution(
        id,
        "Read",
        scope,
        callId,
        Optional.empty(),
        status,
        exitCode,
        0,
        List.of(),
        scope == CallScope.MAIN ? Optional.empty() : Optional.of("child-agent"));
  }

  private static SessionDetail detail(
      NormalizedAgent agent,
      String id,
      Path raw,
      NormalizedSessionArtifact artifact,
      long tools,
      long failed) {
    var row =
        new SessionRow(
            agent.getValue() + ":" + id,
            agent.getValue(),
            id,
            "Synthetic",
            "",
            "",
            "",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:01Z",
            1,
            0,
            0,
            "synthetic",
            "",
            "fixture",
            0,
            0,
            tools,
            0,
            0,
            0,
            0,
            0,
            failed,
            0,
            0,
            0,
            raw == null ? "" : raw.toString());
    return artifact == null
        ? SessionDetail.rowOnly(row, PayloadVisibility.STANDARD)
        : SessionDetailAssembler.assemble(row, artifact, PayloadVisibility.STANDARD, "fixture", 1);
  }
}
