package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/** 验证逻辑轮次跨内容单元后仍保留精确计数，且不构造无限增长的成员数组。 */
class SessionContentProjectionTest {
  @Test
  void oneLogicalRoundCrossesUnitsWithoutLeakingAllMemberIds() throws Exception {
    var content = content();
    var rows =
        SessionContentProjection.rounds(
            SessionDetailParityAnalyzerTest.healthDetail(false, 0), content);
    assertThat(rows).hasSize(1);
    assertThat(rows.getFirst().callCount()).isEqualTo(10234);
    assertThat(rows.getFirst().calls()).isEmpty();
    assertThat(rows.getFirst().parity())
        .containsEntry("summary", "synthetic response 1")
        .containsEntry("summaryRole", "assistant");
    assertThat(rows.getFirst().tokens().total()).isEqualTo(20468);
  }

  @Test
  void httpListsAndRoundMembersKeepExactTotalsAndReachLastCall() {
    var original = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var detail =
        new com.feipi.session.browser.application.sessiondetail.SessionDetail(
            original.sessionRow(),
            List.of(),
            List.of(),
            original.visibility(),
            "synthetic-content",
            NormalizedConstants.SCHEMA_VERSION,
            "synthetic-content-v1",
            1,
            20468);
    var content = content();
    var annotated =
        new com.feipi.session.browser.application.SessionDetailUseCase.AnnotatedDetailContext(
            detail,
            com.feipi.session.browser.query.api.SessionAnomalySummary.empty(
                detail.sessionRow().sessionKey()),
            null,
            content);
    var handler =
        new SessionDetailApiHandler(
            ctx ->
                new SessionDetailApiHandler.LoadedDetail(
                    new SessionDetailApiResponses.SessionDetailFilterEcho(
                        "codex", "health", "standard", "", ""),
                    annotated,
                    "/synthetic",
                    false));
    var service =
        new SessionApiService(
            (key, visibility) ->
                Optional.of(
                    new com.feipi.session.browser.application.SessionDetailUseCase.DetailContext(
                        detail, null, content)));
    var members = new SessionApiHandler(service);
    io.javalin.testtools.JavalinTest.test(
        io.javalin.Javalin.create(
            config -> {
              config.routes.get("/rounds", handler::handleRounds);
              config.routes.get("/payloads", handler::handlePayloads);
              config.routes.get("/metrics", handler::handleMetrics);
              config.routes.get("/diagnostics", handler::handleDiagnostics);
              config.routes.get("/round/1", ctx -> members.handleRound(ctx, "codex", "health", 1));
              config.routes.get(
                  "/tail",
                  ctx ->
                      members.handlePayload(ctx, "codex", "health", "main:resp:synthetic-10234"));
              config.routes.get(
                  "/attribution-tail",
                  ctx -> members.handleAttribution(ctx, "codex", "health", 1, 10234, "response"));
            }),
        (app, client) -> {
          var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
          var rounds = mapper.readTree(client.get("/rounds").body().string());
          assertThat(rounds.path("total").asLong()).isEqualTo(1);
          assertThat(rounds.at("/rounds/0/callCount").asInt()).isEqualTo(10234);
          var metrics = mapper.readTree(client.get("/metrics").body().string());
          assertThat(metrics.path("roundCount").asInt()).isEqualTo(1);
          assertThat(metrics.path("payloadCount").asInt()).isEqualTo(20468);
          assertThat(metrics.at("/parity/workloadCalls").asLong()).isEqualTo(10234);
          var tail = client.get("/tail");
          assertThat(tail.code()).isEqualTo(200);
          assertThat(tail.body().string()).contains("synthetic response 10234");
          var attribution = client.get("/attribution-tail");
          assertThat(attribution.code()).isEqualTo(200);
          assertThat(attribution.body().string()).contains("synthetic-10234");
          assertThat(metrics.at("/parity/contentMeasured").asBoolean()).isTrue();
          var diagnostics = mapper.readTree(client.get("/diagnostics").body().string());
          assertThat(diagnostics.at("/parity/contentMeasured").asBoolean()).isTrue();
          assertThat(diagnostics.at("/parity/toolImpactAvailable").asBoolean()).isFalse();
          assertThat(diagnostics.path("parity").has("toolImpact")).isFalse();
          assertThat(diagnostics.path("parity").has("payloadGaps")).isFalse();
          int payloads = 0;
          String next = null;
          do {
            var response =
                client.get("/payloads?limit=500" + (next == null ? "" : "&cursor=" + next));
            assertThat(response.code()).isEqualTo(200);
            var page = mapper.readTree(response.body().string());
            assertThat(page.path("total").asLong()).isEqualTo(20468);
            payloads += page.path("payloads").size();
            next = page.path("nextCursor").isNull() ? null : page.path("nextCursor").asText();
          } while (next != null);
          assertThat(payloads).isEqualTo(20468);
          int calls = 0;
          do {
            var response =
                client.get("/round/1?limit=500" + (next == null ? "" : "&cursor=" + next));
            assertThat(response.code()).isEqualTo(200);
            var page = mapper.readTree(response.body().string());
            assertThat(page.path("total").asLong()).isEqualTo(10234);
            calls += page.at("/round/calls").size();
            next = page.path("nextCursor").isNull() ? null : page.path("nextCursor").asText();
          } while (next != null);
          assertThat(calls).isEqualTo(10234);
        });
  }

  @Test
  void evidencedMainAndUnconfirmedChildKeepSeparateCountsAndPayloads() throws Exception {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var main = call(1, "token_usage_record:synthetic-main");
    var child =
        new NormalizedCall(
            "child-SR1",
            2,
            "C2",
            CallScope.SUBAGENT,
            Optional.of(main.callId()),
            Optional.of("synthetic-spawn"),
            Optional.of("child-task"),
            "synthetic-model",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(),
            List.of(Map.of("type", "text", "role", "assistant", "text", "synthetic child output")),
            Map.of(),
            Map.of(),
            Optional.of("child"),
            Optional.of("spawn_agent"));
    var artifact =
        new com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            List.of(main, child),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var content = NormalizedSessionContent.fromArtifact(artifact);
    var rows = SessionContentProjection.rounds(detail, content);
    assertThat(rows).hasSize(2);
    assertThat(rows.getFirst().parity()).containsEntry("modelCallEvidence", "response_usage");
    assertThat(rows.getLast().parity()).containsEntry("modelCallEvidence", "");
    assertThat(rows.getLast().parentCallId()).isEqualTo(main.callId());
    var reader =
        new com.feipi.session.browser.application.sessiondetail.SessionContentReader(content, 0);
    assertThat(reader.payload("round:resp:1", detail.visibility()).orElseThrow().content())
        .endsWith("synthetic response 1")
        .doesNotContain("synthetic child output");
    assertThat(reader.payload("round:resp:2", detail.visibility()).orElseThrow().content())
        .endsWith("synthetic child output")
        .doesNotContain("synthetic response 1");
    assertThat(reader.payload("sa:resp:child-SR1", detail.visibility()).orElseThrow().content())
        .isEqualTo("synthetic child output");
  }

  @Test
  void largeContentUsesCallProvenanceAndMeasuredCacheSignalsInsteadOfRowUnknown() throws Exception {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var content = content();
    var rows = SessionContentProjection.rounds(detail, content);
    assertThat(rows.getFirst().tokens().provenance().freshInput()).isEqualTo("provider_reported");
    var result = SessionDetailParityAnalyzer.analyze(detail, null, content, false);
    assertThat(result.metrics)
        .containsEntry("lowCacheRoundsAvailable", true)
        .containsEntry("lowCacheRounds", 1L)
        .containsEntry("freshSpikeRounds", 0L);
    assertThat(result.diagnostics).containsEntry("agentsAvailable", true);
    var agents = (List<?>) result.diagnostics.get("agents");
    assertThat(agents).hasSize(1);
    var main = (Map<?, ?>) agents.getFirst();
    assertThat(main.get("llmCalls")).isEqualTo(10234L);
    var segments = (PageApiDtos.TokenSegments) main.get("tokenSegments");
    assertThat(segments.total()).isEqualTo(20468);
    assertThat(segments.provenance().freshInput()).isEqualTo("provider_reported");
    assertThat(segments.provenance().unknownSessionCount()).isZero();
  }

  @Test
  void agentTokenGroupsDoNotBorrowSessionUsageOrMergeChildIntoMain() {
    var base = call(2);
    var child =
        new NormalizedCall(
            base.callId(),
            base.callIndex(),
            base.callKey(),
            CallScope.SUBAGENT,
            Optional.of("synthetic-1"),
            Optional.empty(),
            base.turnId(),
            base.model(),
            base.timestamp(),
            new NormalizedCallUsage(3, 5, 0, 7, 15),
            base.request(),
            base.response(),
            base.sourceUnitRefRanges(),
            base.sourceUnits(),
            base.attributionCandidates(),
            base.usageSource(),
            Optional.of("synthetic-child"),
            Optional.empty());
    var content =
        NormalizedSessionContent.fromLists(
            new NormalizedContentHeader(
                NormalizedConstants.SCHEMA_VERSION,
                NormalizedAgent.CODEX,
                new NormalizedSessionMetadata(Map.of()),
                Map.of(
                    "calls",
                    2L,
                    "toolExecutions",
                    0L,
                    "diagnostics",
                    0L,
                    "sourceFiles",
                    0L,
                    "sourceUnitCatalog",
                    0L,
                    "sourceUnitSequenceEntries",
                    0L)),
            List.of(),
            List.of(call(1), child),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var result =
        SessionDetailParityAnalyzer.analyze(
            SessionDetailParityAnalyzerTest.healthDetail(false, 0), null, content, false);
    var agents = (List<?>) result.diagnostics.get("agents");
    assertThat(agents).hasSize(2);
    var main = (Map<?, ?>) agents.getFirst();
    var subagent = (Map<?, ?>) agents.getLast();
    assertThat(((PageApiDtos.TokenSegments) main.get("tokenSegments")).total()).isEqualTo(2);
    assertThat(((PageApiDtos.TokenSegments) subagent.get("tokenSegments")).total()).isEqualTo(15);
    assertThat(subagent.get("subagentId")).isEqualTo("synthetic-child");
  }

  private static NormalizedSessionContent content() {
    var calls =
        IntStream.rangeClosed(1, 10234).mapToObj(SessionContentProjectionTest::call).toList();
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                10234L,
                "toolExecutions",
                0L,
                "diagnostics",
                0L,
                "sourceFiles",
                0L,
                "sourceUnitCatalog",
                0L,
                "sourceUnitSequenceEntries",
                0L)),
        List.of(),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(int index) {
    return call(index, "synthetic-" + index);
  }

  private static NormalizedCall call(int index, String id) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.of("same-turn"),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(1, 0, 0, 1, 2),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(Map.of("role", "assistant", "type", "text", "text", "synthetic response " + index)),
        Map.of(),
        Map.of(
            "freshInputTokenPrecision",
            "provider_reported",
            "cacheReadTokenPrecision",
            "provider_reported",
            "cacheWriteTokenPrecision",
            "provider_reported",
            "outputTokenPrecision",
            "provider_reported"),
        Optional.empty(),
        Optional.empty());
  }
}
