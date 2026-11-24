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
  void firstUserPromptLinksToTheCallThatContainsTheUserText() {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var content = content(List.of(call(1), call(2, "synthetic-2", "synthetic first question")));
    var annotated =
        new com.feipi.session.browser.application.SessionDetailUseCase.AnnotatedDetailContext(
            detail,
            com.feipi.session.browser.query.api.SessionAnomalySummary.empty(
                detail.sessionRow().sessionKey()),
            null,
            content);
    var meta =
        new SessionDetailApiHandler(
            ctx ->
                new SessionDetailApiHandler.LoadedDetail(
                    new SessionDetailApiResponses.SessionDetailFilterEcho(
                        "codex", "health", "standard", "", ""),
                    annotated,
                    "/synthetic",
                    false));
    var payload =
        new SessionApiHandler(
            new SessionApiService(
                (key, visibility) ->
                    Optional.of(
                        new com.feipi.session.browser.application.SessionDetailUseCase
                            .DetailContext(detail, null, content))));
    io.javalin.testtools.JavalinTest.test(
        io.javalin.Javalin.create(
            config -> {
              config.routes.get("/meta", meta::handleMeta);
              config.routes.get(
                  "/payload/{id}",
                  ctx -> payload.handlePayload(ctx, "codex", "health", ctx.pathParam("id")));
            }),
        (app, client) -> {
          var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
          var body = mapper.readTree(client.get("/meta").body().string());
          assertThat(body.path("firstUserPrompt").asText()).isEqualTo("synthetic first question");
          String payloadId = body.path("firstUserPromptPayloadId").asText();
          assertThat(payloadId).isEqualTo("main:req:synthetic-2");
          var preparation =
              mapper.readTree(client.get("/payload/main:req:synthetic-1").body().string());
          assertThat(preparation.path("content").asText()).isEmpty();
          var question = mapper.readTree(client.get("/payload/" + payloadId).body().string());
          assertThat(question.path("content").asText()).isEqualTo("synthetic first question");
          var answer =
              mapper.readTree(client.get("/payload/main:resp:synthetic-2").body().string());
          assertThat(answer.path("content").asText()).isEqualTo("synthetic response 2");
        });
  }

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
              config.routes.get("/execution", handler::handleExecution);
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
          var execution = mapper.readTree(client.get("/execution").body().string());
          assertThat(execution.path("items").size()).isEqualTo(20);
          assertThat(execution.path("total").asLong()).isEqualTo(10234);
          var located =
              mapper.readTree(client.get("/execution?target=synthetic-10234").body().string());
          assertThat(located.path("items").size()).isEqualTo(1);
          assertThat(located.at("/items/0/group/id").asText()).isEqualTo("synthetic-10234");
          assertThat(located.path("offset").asLong()).isEqualTo(10233);
          assertThat(client.get("/execution?limit=101").code()).isEqualTo(400);
          String executionCursor = execution.path("nextCursor").asText();
          assertThat(client.get("/execution?status=failed&cursor=" + executionCursor).code())
              .isEqualTo(400);
          var nextExecution =
              mapper.readTree(client.get("/execution?cursor=" + executionCursor).body().string());
          assertThat(nextExecution.at("/items/0/group/id").asText()).isEqualTo("synthetic-21");
          var head = mapper.readTree(client.get("/execution?summary=1").body().string());
          assertThat(head.path("items").size()).isZero();
          assertThat(head.path("diagnostics")).isEqualTo(execution.path("diagnostics"));
          var row = mapper.readTree(client.get("/rounds?target=1&limit=1").body().string());
          assertThat(row.at("/rounds/0/roundIndex").asInt()).isOne();
          assertThat(client.get("/rounds?target=2").code()).isEqualTo(404);
          assertThat(client.get("/rounds?target=0").code()).isEqualTo(400);
          var focused =
              mapper.readTree(
                  client
                      .get("/round/1?target_kind=call&target=synthetic-10233&limit=1")
                      .body()
                      .string());
          assertThat(focused.path("offset").asLong()).isEqualTo(10232);
          assertThat(focused.at("/round/calls/0/callId").asText()).isEqualTo("synthetic-10233");
          assertThat(focused.at("/round/calls").size()).isOne();
          var after =
              mapper.readTree(
                  client
                      .get("/round/1?cursor=" + focused.path("nextCursor").asText())
                      .body()
                      .string());
          assertThat(after.at("/round/calls/0/callId").asText()).isEqualTo("synthetic-10234");
          assertThat(client.get("/round/1?target=missing-tool").code()).isEqualTo(404);
          var diagnostics = mapper.readTree(client.get("/diagnostics").body().string());
          assertThat(diagnostics.at("/parity/contentMeasured").asBoolean()).isTrue();
          assertThat(diagnostics.at("/parity/toolCalls").longValue()).isZero();
          assertThat(diagnostics.at("/parity/toolCallsAvailable").asBoolean()).isTrue();
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
  void confirmedSideTaskMembersAreCountedIndividuallyOnEveryRoundPage() {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var content = content(List.of(sideTaskCall(1), sideTaskCall(2), call(3, "unconfirmed")));
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
    io.javalin.testtools.JavalinTest.test(
        io.javalin.Javalin.create(config -> config.routes.get("/rounds", handler::handleRounds)),
        (app, client) -> {
          var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
          var first = mapper.readTree(client.get("/rounds?limit=1").body().string());
          var next = first.path("nextCursor").asText();
          assertThat(next).isNotBlank();
          var second =
              mapper.readTree(client.get("/rounds?limit=1&cursor=" + next).body().string());
          assertThat(first.at("/rounds/0/callCount").asInt()).isEqualTo(2);
          for (var page : List.of(first, second)) {
            assertThat(page.path("roundCount").asInt()).isEqualTo(2);
            assertThat(page.path("modelCallCount").asInt()).isEqualTo(2);
            assertThat(page.path("recordGroupCount").asInt()).isEqualTo(1);
          }
        });
  }

  private static NormalizedCall sideTaskCall(int index) {
    return new NormalizedCall(
        "token_usage_record:synthetic-" + index,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.of("synthetic-side-task"),
        "synthetic-model",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(Map.of("type", "codex_context_side_task_id", "text", "synthetic-side-task")),
        Map.of(),
        Map.of(),
        Optional.empty(),
        Optional.empty());
  }

  @Test
  void sideTaskGroupsCallsWithoutLosingUsageOrMeaningfulUserPreview() throws Exception {
    var calls =
        List.of(
            sideTaskCall(1, "first", "S", true),
            sideTaskCall(2, "first", "The actual user question", false),
            sideTaskCall(3, "second", "S\n```\nsynthetic code\n```\n\n可见的用户正文", false),
            sideTaskCall(4, "third", "X", false));
    var content = content(calls);
    var rows =
        SessionContentProjection.rounds(
            SessionDetailParityAnalyzerTest.healthDetail(false, 0), content);
    assertThat(rows).hasSize(3);
    var first = rows.getFirst();
    assertThat(first.callCount()).isEqualTo(2);
    assertThat(first.tokens().total()).isEqualTo(4);
    assertThat(first.parity())
        .containsEntry("summary", "The actual user question")
        .containsEntry("userTask", true)
        .containsEntry("taskStartedAt", "2026-01-01T01:00:00Z")
        .containsEntry("taskDurationMs", 900L);
    assertThat(rows.get(1).parity()).containsEntry("summary", "可见的用户正文");
    assertThat(rows.getLast().callCount()).isEqualTo(1);
    assertThat(rows.getLast().parity())
        .containsEntry("summary", "X")
        .doesNotContainKey("taskDurationMs");
  }

  @Test
  void standaloneCompactionUsesItsSourcePhaseAsTheRoundSummary() throws Exception {
    var content = content(List.of(sideTaskCall(1, "prep", "", false)));
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var row = SessionContentProjection.rounds(detail, content).getFirst();
    assertThat(row.callCount()).isEqualTo(1);
    assertThat(row.parity())
        .containsEntry("summary", "上下文压缩")
        .containsEntry("summaryRole", "")
        .containsEntry("isUserInput", false)
        .containsEntry("requestAvailable", true)
        .containsEntry("responseAvailable", true);
  }

  @Test
  void groupedRoundHttpReportsUsageOnlyResponseAndPhases() throws Exception {
    var content =
        content(
            List.of(
                sideTaskCall(1, "first", "", true),
                sideTaskCall(2, "first", "A visible question", false)));
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var handler =
        new SessionApiHandler(
            new SessionApiService(
                (key, visibility) ->
                    Optional.of(
                        new com.feipi.session.browser.application.SessionDetailUseCase
                            .DetailContext(detail, null, content))));
    io.javalin.testtools.JavalinTest.test(
        io.javalin.Javalin.create(
            cfg -> cfg.routes.get("/round", ctx -> handler.handleRound(ctx, "codex", "health", 1))),
        (app, client) -> {
          var json =
              new com.fasterxml.jackson.databind.ObjectMapper()
                  .readTree(client.get("/round?limit=10").body().string());
          var calls = json.path("round").path("calls");
          assertThat(calls.size()).isEqualTo(2);
          assertThat(calls.get(0).path("phaseLabel").asText()).isEqualTo("上下文压缩");
          assertThat(calls.get(0).path("responseAvailable").asBoolean()).isTrue();
          assertThat(calls.get(0).path("requestAvailable").asBoolean()).isTrue();
          assertThat(calls.get(1).path("phaseLabel").asText()).isEqualTo("压缩后调用");
          assertThat(calls.get(1).path("requestAvailable").asBoolean()).isTrue();
        });
  }

  private static NormalizedCall sideTaskCall(int index, String task, String text, boolean timing) {
    var base = call(index, "token_usage_record:side-" + index, text);
    var units = new java.util.ArrayList<>(base.sourceUnits());
    if (index == 1) {
      units.removeIf(unit -> "assistant".equals(unit.get("role")));
      units.add(
          Map.of("role", "context", "type", "codex_context_response_usage", "text", "observed"));
      units.add(Map.of("role", "context", "type", "codex_context_input_tokens", "text", "1"));
      units.add(
          Map.of(
              "role", "context", "type", "codex_context_response_compaction", "text", "identity"));
    } else if (index == 2) {
      units.add(Map.of("role", "context", "type", "codex_context_boundary", "text", "compacted"));
    }
    units.add(Map.of("role", "context", "type", "codex_context_side_task_id", "text", task));
    if (timing) {
      units.add(
          Map.of(
              "role",
              "context",
              "type",
              "codex_context_side_task_started_at",
              "text",
              "2026-01-01T01:00:00Z"));
      units.add(
          Map.of("role", "context", "type", "codex_context_side_task_duration_ms", "text", "900"));
    }
    return new NormalizedCall(
        base.callId(),
        index,
        base.callKey(),
        base.scope(),
        base.parentCallId(),
        base.parentToolCallId(),
        Optional.of(task),
        base.model(),
        base.timestamp(),
        base.usage(),
        base.request(),
        base.response(),
        base.sourceUnitRefRanges(),
        units,
        base.attributionCandidates(),
        base.usageSource(),
        base.subagentId(),
        base.parentToolName());
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
    return content(
        IntStream.rangeClosed(1, 10234).mapToObj(SessionContentProjectionTest::call).toList());
  }

  private static NormalizedSessionContent content(List<NormalizedCall> calls) {
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                (long) calls.size(),
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
    return call(index, id, "");
  }

  private static NormalizedCall call(int index, String id, String user) {
    var response =
        Map.<String, Object>of(
            "role", "assistant", "type", "text", "text", "synthetic response " + index);
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
        user.isEmpty()
            ? List.of(response)
            : List.of(Map.of("role", "user", "type", "text", "text", user), response),
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
