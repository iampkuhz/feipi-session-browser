package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.source.SourceToolObservation;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/** 执行动作按声明身份归组；计量、分页和证据范围互不冒充。 */
class SessionExecutionProjectionTest {
  @Test
  void executionContextKeepsMainTargetsAnonymousToolsAndKnownOwnersDistinct() throws Exception {
    var main = contextTool("main-target", CallScope.MAIN, "unknown", "target");
    var missing = contextTool("missing", CallScope.SUBAGENT, "unknown", "");
    var anonymous =
        contextTool("anonymous", CallScope.SUBAGENT, "unknown", "unknown-sidechain:synthetic");
    var conflicting = contextTool("conflicting", CallScope.SUBAGENT, "call-1", "target");
    assertThat(SessionContextLabels.executionContext(main, null)).isEqualTo("main");
    assertThat(SessionContextLabels.executionContext(missing, null)).isEmpty();
    assertThat(SessionContextLabels.executionContext(anonymous, null)).isEmpty();
    assertThat(SessionContextLabels.executionContext(conflicting, "main")).isEqualTo("main");
    var content =
        content(
            List.of(main, missing, anonymous, conflicting),
            List.of(call(1, List.of("conflicting"), List.of())));
    assertThat(
            SessionExecutionProjection.read(
                    content, "conflict", null, 20, null, "all", "subagent:target")
                .items())
        .isEmpty();
    assertThat(SessionExecutionProjection.diagnostics(content, "subagent:target").totalTools())
        .isZero();
    assertThat(
            SessionExecutionProjection.read(content, "main", null, 20, null, "all", "main").items())
        .extracting(item -> item.tool().toolCallId())
        .containsExactly("conflicting", "main-target");
    assertThat(SessionExecutionProjection.diagnostics(content, "main").totalTools()).isEqualTo(2);
  }

  @Test
  void selectedToolOnlyChildSupportsFailedTargetAndPagingWithoutGrantingCumulativeIdentity()
      throws Exception {
    var content = toolOnlyChildContent();
    var failed =
        SessionExecutionProjection.read(
            content,
            "child-failed",
            null,
            1,
            "child-command",
            "failed",
            "subagent:synthetic-child");
    assertThat(failed.total()).isEqualTo(1);
    assertThat(failed.offset()).isZero();
    assertThat(failed.nextCursor()).isNull();
    assertThat(failed.items().getFirst().tool().toolCallId()).isEqualTo("child-command");
    var selected = SessionExecutionProjection.diagnostics(content, "subagent:synthetic-child");
    assertThat(selected.longOperations().candidates()).isEmpty();
    assertThat(selected.workloadSignals().candidates()).isEmpty();
  }

  private static NormalizedToolExecution contextTool(
      String id, CallScope scope, String owner, String child) {
    return new NormalizedToolExecution(
        id,
        "exec_command",
        scope,
        owner,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        null,
        List.of(),
        child.isEmpty() ? Optional.empty() : Optional.of(child),
        Optional.empty());
  }

  @Test
  void selectedToolOnlyChildRetainsItsUnownedExecutionWithoutParentSpawn() throws Exception {
    var content = toolOnlyChildContent();
    var all = SessionExecutionProjection.read(content, "all-child", null, 20, null, "all");
    assertThat(all.items())
        .extracting(item -> item.tool().toolCallId())
        .containsExactly("parent-spawn", "child-command");
    var unowned = all.items().get(1);
    assertThat(unowned.group().response()).isFalse();
    assertThat(unowned.tool().declaredByCallId()).isEqualTo("unknown");
    assertThat(unowned.tool().durationMs()).isEqualTo(500L);
    assertThat(unowned.tool().exitCode()).isEqualTo(7);
    var selected =
        SessionExecutionProjection.read(
            content, "selected-child", null, 20, null, "all", "subagent:synthetic-child");
    assertThat(selected.items()).hasSize(1);
    assertThat(selected.items().getFirst().tool().toolCallId()).isEqualTo("child-command");
    assertThat(selected.items().getFirst().tool().declaredByCallId()).isEqualTo("unknown");
    assertThat(selected.items().getFirst().group().response()).isFalse();
  }

  @Test
  void selectedToolOnlyChildDiagnosticsRetainItsDurationAndFailure() throws Exception {
    var content = toolOnlyChildContent();
    var all = SessionExecutionProjection.diagnostics(content);
    assertThat(all.totalTools()).isEqualTo(2);
    assertThat(all.firstFailureTool().toolCallId()).isEqualTo("child-command");
    var selected = SessionExecutionProjection.diagnostics(content, "subagent:synthetic-child");
    org.assertj.core.api.SoftAssertions.assertSoftly(
        softly -> {
          softly.assertThat(selected.totalTools()).isEqualTo(1);
          softly.assertThat(selected.measuredTools()).isEqualTo(1);
          softly.assertThat(selected.measuredWorkMs()).isEqualTo(500.0);
          softly.assertThat(selected.failures()).isEqualTo(1);
          softly.assertThat(selected.firstFailure()).isEqualTo("child-command");
          softly.assertThat(selected.firstFailureTool()).isEqualTo(all.firstFailureTool());
        });
  }

  private static NormalizedSessionContent toolOnlyChildContent() {
    var spawn =
        new NormalizedToolExecution(
            "parent-spawn",
            "spawn_agent",
            CallScope.MAIN,
            "call-1",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            null,
            List.of(),
            Optional.of("synthetic-child"),
            Optional.empty());
    var child =
        new NormalizedToolExecution(
            "child-command",
            "exec_command",
            CallScope.SUBAGENT,
            "unknown",
            Optional.empty(),
            Optional.empty(),
            Optional.of(7),
            500L,
            List.of(),
            Optional.of("synthetic-child"),
            Optional.of(
                new SourceToolObservation(
                    "child-command",
                    500_000_000L,
                    7,
                    "completed",
                    null,
                    "executor_reported",
                    "codex:exec_command_end#event[3]",
                    null)));
    return content(List.of(spawn, child), List.of(call(1, List.of("parent-spawn"), List.of())));
  }

  @Test
  void ownerIndependentInputGetsSafeExecutionPreviewWithoutAModelResponse() throws Exception {
    var tool =
        new NormalizedToolExecution(
            "synthetic-orphan",
            "exec_command",
            CallScope.SUBAGENT,
            "unknown",
            Optional.empty(),
            Optional.empty(),
            Optional.of(7),
            500L,
            List.of(),
            Optional.of("synthetic-child"),
            Optional.empty());
    String key = "tool-input:5:0:synthetic/child#event[1]";
    String input =
        "{\"cmd\":\"node synthetic-check.js --api-key=synthetic-secret token=synthetic-private-value <script>\"}";
    for (boolean certified : List.of(true, false)) {
      var payload =
          new java.util.LinkedHashMap<String, Object>(
              Map.of(
                  "type",
                  "tool_use",
                  "id",
                  tool.toolCallId(),
                  "name",
                  tool.name(),
                  "input",
                  input));
      if (certified)
        payload.put(
            "independent",
            Map.of(
                "ordinal", "5", "slot", "0", "scope", "subagent", "subagent", "synthetic-child"));
      String actualKey = certified ? key : "bare";
      var entry =
          new com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry(
              actualKey,
              "synthetic/child",
              "synthetic/child#event[1]",
              "tool_use",
              certified ? "independent_tool_input.v1" : "",
              com.feipi.session.browser.domain.normalized.SourceUnitDirection.RESPONSE,
              1,
              0,
              com.feipi.session.browser.domain.normalized.ByteRange.empty(),
              "",
              Optional.empty(),
              Optional.of(tool.toolCallId()),
              50,
              Optional.empty(),
              Optional.empty(),
              payload,
              Optional.empty(),
              Optional.empty(),
              List.of());
      var declarations =
          certified
              ? List.<NormalizedCall>of()
              : List.of(call(1, List.of(tool.toolCallId()), List.of()));
      var artifact =
          new com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CODEX,
              List.of(),
              Map.of(),
              declarations,
              List.of(tool),
              List.of(),
              Map.of(actualKey, entry),
              Map.of());
      var content = NormalizedSessionContent.fromArtifact(artifact);
      var page = SessionExecutionProjection.read(content, "orphan", null, 20, null, "all");
      assertThat(page.items()).hasSize(certified ? 1 : 2);
      var summary =
          page.items().stream()
              .filter(item -> item.tool() != null)
              .findFirst()
              .orElseThrow()
              .tool();
      assertThat(summary.declaredByCallId()).isEqualTo("unknown");
      assertThat(summary.durationMs()).isEqualTo(500L);
      assertThat(summary.exitCode()).isEqualTo(7);
      if (certified) {
        assertThat(summary.inputPreview())
            .contains("node synthetic-check.js")
            .doesNotContain("synthetic-secret", "synthetic-private-value");
        assertThat(
                SessionExecutionProjection.diagnostics(content).firstFailureTool().inputPreview())
            .isEqualTo(summary.inputPreview());
      } else assertThat(summary.inputPreview()).isEmpty();
    }
  }

  @Test
  void firstFailureEvidenceIsAnExplicitJsonProperty() {
    var first = failureSummary(7, 0, "failed", "<script>/private/synthetic</script>");
    var diagnostics =
        new SessionExecutionProjection.Diagnostics(1, 0, 0, 1, "signal", List.of(), 0, first);
    var json = new ObjectMapper().valueToTree(diagnostics);
    assertThat(json.has("firstFailureEvidence")).isTrue();
    var evidence = json.path("firstFailureEvidence");
    assertThat(evidence.size()).isEqualTo(3);
    assertThat(evidence.path("kind").asText()).isEqualTo("executor_status");
    assertThat(evidence.path("executorStatus").asText()).isEqualTo("failed");
    assertThat(evidence.path("exitCode").isNull()).isTrue();
    assertThat(evidence.toString()).doesNotContain("script", "private");
    var empty = new SessionExecutionProjection.Diagnostics(0, 0, 0, 0, null, List.of(), 0, null);
    var emptyJson = new ObjectMapper().valueToTree(empty);
    assertThat(emptyJson.has("firstFailureEvidence")).isTrue();
    assertThat(emptyJson.path("firstFailureEvidence").isNull()).isTrue();
  }

  @Test
  void failureEvidencePreservesIndependentOldPredicateAndPriority() {
    Integer[] exits = {null, 0, 7, -1, Integer.MIN_VALUE, Integer.MAX_VALUE};
    String[] executors = {
      null, "failed", "error", "cancelled", "FAILED", " failed", "error ", "completed", "unknown"
    };
    String[] results = {
      null,
      "",
      " ",
      "ok",
      "SUCCESS",
      "Completed",
      "running",
      "pending",
      "queued",
      "ok ",
      " failed",
      "<script>/private/synthetic</script>".repeat(1000)
    };
    for (Integer exit : exits) {
      for (Integer observed : exits) {
        for (String executor : executors) {
          for (String result : results) {
            var tool = failureSummary(exit, observed, executor, result);
            assertFailureEvidence(tool);
            var withoutObservation =
                new ApiResponses.ToolExecutionSummary(
                    "signal",
                    "exec_command",
                    "main",
                    "call-1",
                    result,
                    exit,
                    0L,
                    "",
                    "",
                    "executor_reported",
                    false,
                    null);
            assertFailureEvidence(withoutObservation);
          }
        }
      }
    }
    assertThat(SessionExecutionProjection.failureEvidence(null)).isNull();
  }

  private static void assertFailureEvidence(ApiResponses.ToolExecutionSummary tool) {
    Integer exit =
        tool.observation() != null && tool.observation().exitCode() != null
            ? tool.observation().exitCode()
            : tool.exitCode();
    String explicit = tool.observation() == null ? "" : tool.observation().status();
    boolean oldFailed =
        (exit != null && exit != 0)
            || "failed".equals(explicit)
            || "error".equals(explicit)
            || "cancelled".equals(explicit)
            || (!tool.status().isBlank()
                && !List.of("ok", "success", "completed", "running", "pending", "queued")
                    .contains(tool.status().toLowerCase(java.util.Locale.ROOT)));
    assertThat(SessionExecutionProjection.failed(tool)).isEqualTo(oldFailed);
    var evidence = SessionExecutionProjection.failureEvidence(tool);
    assertThat(evidence != null).isEqualTo(oldFailed);
    if (!oldFailed) return;
    var json = new ObjectMapper().valueToTree(evidence);
    assertThat(json.size()).isEqualTo(3);
    if (exit != null && exit != 0) {
      assertThat(evidence.kind()).isEqualTo("nonzero_exit");
      assertThat(evidence.exitCode()).isEqualTo(exit);
      assertThat(evidence.executorStatus()).isNull();
    } else if (List.of("failed", "error", "cancelled").contains(explicit == null ? "" : explicit)) {
      assertThat(evidence.kind()).isEqualTo("executor_status");
      assertThat(evidence.exitCode()).isNull();
      assertThat(evidence.executorStatus()).isEqualTo(explicit);
    } else {
      assertThat(evidence.kind()).isEqualTo("result_signal");
      assertThat(evidence.exitCode()).isNull();
      assertThat(evidence.executorStatus()).isNull();
    }
    assertThat(json.toString()).doesNotContain("script", "private", "synthetic");
  }

  private static ApiResponses.ToolExecutionSummary failureSummary(
      Integer exit, Integer observedExit, String executor, String result) {
    return new ApiResponses.ToolExecutionSummary(
        "signal",
        "exec_command",
        "main",
        "call-1",
        result,
        exit,
        0L,
        "",
        "",
        "executor_reported",
        true,
        new SourceToolObservation(
            "signal",
            0L,
            observedExit,
            executor,
            null,
            "executor_reported",
            "synthetic:end",
            null));
  }

  @Test
  void executionContextLabelsUseFullCanonicalCallPrefixWithoutAnotherScan() throws Exception {
    var content =
        new CountingContent(
            content(
                List.of(),
                List.of(
                    childCall(1, "violet"),
                    call(2, List.of(), List.of()),
                    childCall(3, "yarrow"))));
    var labels = new SessionContextLabels();
    var page =
        SessionExecutionProjection.read(
            content,
            new SessionExecutionProjection.ReadRequest(
                "labels", null, 1, null, "all", "subagent:yarrow"),
            labels);
    page =
        page.withDiagnostics(
            SessionExecutionProjection.diagnostics(content, "subagent:yarrow", labels), labels);
    assertThat(content.opens).isEqualTo(9);
    assertThat(content.reads).isEqualTo(27);
    var json = new ObjectMapper().valueToTree(page);
    assertThat(json.path("contextLabels").path("subagent:yarrow").asText()).isEqualTo("Agent 2");
  }

  @Test
  void largeCallCatalogReturnsExactlyPageAndDiagnosticReferencesWithoutFullDirectory()
      throws Exception {
    var calls = new ArrayList<NormalizedCall>();
    for (int i = 1; i <= 1200; i++) calls.add(childCall(i, "worker-" + i));
    var tools =
        List.of(
            owned(
                measured(
                    "tail",
                    "exec_command",
                    2_000_000_000L,
                    "subagent",
                    "worker-1200",
                    "executor_reported",
                    1),
                "call-1200"),
            owned(
                measured(
                    "almost-tail",
                    "exec_command",
                    1_000_000_000L,
                    "subagent",
                    "worker-1199",
                    "executor_reported",
                    2),
                "call-1199"));
    var counted = new CountingContent(content(tools, calls));
    var labels = new SessionContextLabels();
    var page =
        SessionExecutionProjection.read(
            counted,
            new SessionExecutionProjection.ReadRequest("small", null, 1, null, "all", ""),
            labels);
    var diagnostics = SessionExecutionProjection.diagnostics(counted, "", labels);
    page = page.withDiagnostics(diagnostics, labels);
    assertThat(page.contextLabels())
        .containsExactlyInAnyOrderEntriesOf(
            Map.of(
                "subagent:worker-1",
                "Agent 0",
                "subagent:worker-1199",
                "Agent 1198",
                "subagent:worker-1200",
                "Agent 1199"));
    assertThat(page.contextLabels()).hasSizeLessThanOrEqualTo(2 * page.items().size() + 69);
    assertThat(diagnostics.totalTools()).isEqualTo(2);
    assertThat(counted.opens).isEqualTo(9);
    assertThat(counted.reads).isEqualTo(10800);
    var selected =
        SessionExecutionProjection.read(
            counted, "selected-large", null, 100, "tail", "all", "subagent:worker-1200");
    assertThat(selected.contextLabels())
        .containsExactlyEntriesOf(Map.of("subagent:worker-1200", "Agent 1199"));
    assertThat(selected.items()).hasSize(1);
  }

  @Test
  void failedSelectionUsesGlobalCallPrefixAndOrphanToolsDoNotInventAuthority() throws Exception {
    var calls =
        List.of(childCall(1, "violet"), call(2, List.of(), List.of()), childCall(3, "yarrow"));
    var failed =
        new NormalizedToolExecution(
            "failed-child",
            "exec_command",
            CallScope.SUBAGENT,
            "call-3",
            Optional.empty(),
            Optional.of("error"),
            Optional.of(1),
            1L,
            List.of(),
            Optional.of("yarrow"),
            Optional.empty());
    var orphan =
        new NormalizedToolExecution(
            "orphan",
            "exec_command",
            CallScope.SUBAGENT,
            "missing",
            Optional.empty(),
            Optional.of("error"),
            Optional.of(1),
            1L,
            List.of(),
            Optional.of("tool-only"),
            Optional.empty());
    var content = content(List.of(failed, orphan), calls);
    var selected =
        SessionExecutionProjection.read(
            content, "failed-selected", null, 100, "failed-child", "failed", "subagent:yarrow");
    assertThat(selected.contextLabels())
        .containsExactlyEntriesOf(Map.of("subagent:yarrow", "Agent 2"));
    assertThat(selected.items()).hasSize(1);
    var target = SessionExecutionProjection.read(content, "orphan", null, 1, "orphan", "failed");
    assertThat(target.contextLabels()).isEmpty();
    assertThat(target.items().getFirst().tool().toolCallId()).isEqualTo("orphan");
    assertThat(
            SessionExecutionProjection.read(
                    content(List.of(), List.of()), "empty", null, 100, null, "all")
                .contextLabels())
        .isEmpty();
  }

  @Test
  void handlerSerializesHintsWithoutChangingDiagnosticsAndKeepsRequestsIsolated() {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var normal =
        content(
            List.of(),
            List.of(childCall(1, "violet"), call(2, List.of(), List.of()), childCall(3, "yarrow")));
    var imported = content(List.of(), List.of(call(1, List.of(), List.of())));
    var handler =
        new SessionDetailApiHandler(
            ctx ->
                new SessionDetailApiHandler.LoadedDetail(
                    new SessionDetailApiResponses.SessionDetailFilterEcho(
                        "codex", "health", "standard", "", ""),
                    new com.feipi.session.browser.application.SessionDetailUseCase
                        .AnnotatedDetailContext(
                        detail,
                        com.feipi.session.browser.query.api.SessionAnomalySummary.empty(
                            detail.sessionRow().sessionKey()),
                        null,
                        ctx.path().equals("/empty")
                            ? null
                            : ctx.path().equals("/imported") ? imported : normal),
                    "/synthetic",
                    ctx.path().equals("/imported")));
    io.javalin.testtools.JavalinTest.test(
        io.javalin.Javalin.create(
            config -> {
              config.routes.get("/normal", handler::handleExecution);
              config.routes.get("/imported", handler::handleExecution);
              config.routes.get("/empty", handler::handleExecution);
            }),
        (app, client) -> {
          var mapper = new ObjectMapper();
          for (String route :
              List.of(
                  "/normal",
                  "/imported",
                  "/empty",
                  "/normal?agent_context=subagent:yarrow&limit=1&target=call-3")) {
            var response = client.get(route);
            assertThat(response.code()).isEqualTo(200);
            var body = mapper.readTree(response.body().string());
            assertThat(body.path("contextLabels").isObject()).isTrue();
            assertThat(body.path("diagnostics").has("contextLabels")).isFalse();
            if (route.equals("/imported"))
              assertThat(body.path("contextLabels").size()).isEqualTo(1);
            if (route.equals("/empty")) assertThat(body.path("contextLabels").isEmpty()).isTrue();
            if (route.startsWith("/normal"))
              assertThat(body.path("contextLabels").path("subagent:yarrow").asText())
                  .isEqualTo("Agent 2");
            if (route.contains("agent_context"))
              assertThat(body.path("contextLabels").size()).isEqualTo(1);
          }
        });
  }

  private static final class CountingContent implements NormalizedSessionContent {
    private final NormalizedSessionContent delegate;
    private int opens;
    private int reads;

    private CountingContent(NormalizedSessionContent delegate) {
      this.delegate = delegate;
    }

    @Override
    public NormalizedContentHeader header() {
      return delegate.header();
    }

    @Override
    public ContentCursor openCursor() throws java.io.IOException {
      opens++;
      var cursor = delegate.openCursor();
      return new ContentCursor() {
        @Override
        public boolean hasNext() throws java.io.IOException {
          return cursor.hasNext();
        }

        @Override
        public com.feipi.session.browser.domain.normalized.NormalizedContentUnit next()
            throws java.io.IOException {
          reads++;
          return cursor.next();
        }

        @Override
        public void close() throws java.io.IOException {
          cursor.close();
        }
      };
    }
  }

  @Test
  void qualifiedOperationPreviewIsSharedByProcessAndDiagnosticsWithoutChangingFacts()
      throws Exception {
    String input =
        "{\"target\":\"synthetic-child\",\"message\":\"Synthetic followup\",\"interrupt\":true}";
    var original = tool("synthetic-input", 1_000_000_000L, 1);
    var tool =
        new NormalizedToolExecution(
            original.toolCallId(),
            "send_input",
            original.scope(),
            original.declaredByCallId(),
            original.resultConsumedByCallId(),
            original.status(),
            original.exitCode(),
            original.durationMs(),
            original.filesTouched(),
            original.subagentId(),
            original.observation(),
            List.of(
                new com.feipi.session.browser.domain.normalized.NormalizedCollaborationAction(
                    "input",
                    "declaration",
                    Optional.empty(),
                    Optional.of("synthetic-child"),
                    "synthetic:event",
                    Optional.empty(),
                    "explicit_target",
                    "main_context")));
    var base = call(1, List.of(tool.toolCallId()), List.of());
    var call =
        new NormalizedCall(
            base.callId(),
            base.callIndex(),
            base.callKey(),
            base.scope(),
            base.parentCallId(),
            base.parentToolCallId(),
            base.turnId(),
            base.model(),
            base.timestamp(),
            base.usage(),
            base.request(),
            base.response(),
            base.sourceUnitRefRanges(),
            List.of(
                Map.of(
                    "type",
                    "function_call",
                    "call_id",
                    tool.toolCallId(),
                    "name",
                    tool.name(),
                    "arguments",
                    input)),
            base.attributionCandidates(),
            base.usageSource());
    var content =
        content(List.of(tool), List.of(call, call(2, List.of(), List.of(tool.toolCallId()))));
    var page = SessionExecutionProjection.read(content, "synthetic-scope", null, 100, null, "all");
    var projected = page.items().stream().filter(item -> item.tool() != null).toList();
    assertThat(projected).hasSize(1);
    var summary = projected.getFirst().tool();
    assertThat(summary.inputPreview()).isEqualTo("追加输入：Synthetic followup");
    assertThat(summary.name()).isEqualTo("send_input");
    assertThat(summary.toolCallId()).isEqualTo(tool.toolCallId());
    assertThat(summary.declaredByCallId()).isEqualTo("call-1");
    assertThat(summary.durationMs()).isEqualTo(1000L);
    var diagnostics = SessionExecutionProjection.diagnostics(content);
    assertThat(diagnostics.firstFailureTool().inputPreview()).isEqualTo(summary.inputPreview());
    assertThat(diagnostics.longestByName().getFirst().inputPreview())
        .isEqualTo(summary.inputPreview());
    assertThat(diagnostics.longOperations().totalTools()).isZero();
    assertThat(diagnostics.totalTools()).isEqualTo(1);
    assertThat(diagnostics.measuredTools()).isEqualTo(1);
    assertThat(diagnostics.measuredWorkMs()).isEqualTo(1000.0);
    assertThat(diagnostics.failures()).isEqualTo(1);
    assertThat(
            com.feipi.session.browser.application.sessiondetail.ToolInputContents.inline(call)
                .get(tool.toolCallId())
                .input())
        .isEqualTo(input);
  }

  @Test
  void workloadSignalsPoisonBothKnownConflictGroupsWithoutDoubleCounting() throws Exception {
    var tools =
        List.of(
            measured("spawn", "spawn_agent", null, "main", "", "", 0),
            measured("main", "exec_command", 1L, "main", "", "executor_reported", 1),
            owned(
                measured("a", "exec_command", 2L, "subagent", "A", "executor_reported", 2),
                "call-2"),
            owned(
                measured("b", "exec_command", 3L, "subagent", "B", "executor_reported", 3),
                "call-3"),
            measured("conflict", "exec_command", 100L, "subagent", "A", "executor_reported", 4));
    var calls =
        List.of(
            call(1, List.of("main", "conflict"), List.of()), childCall(2, "A"), childCall(3, "B"));
    var diagnostics = SessionExecutionProjection.diagnostics(content(tools, calls));
    var json = new ObjectMapper().valueToTree(diagnostics).path("workloadSignals");
    assertThat(json.path("totalTools").asLong()).isEqualTo(4);
    assertThat(json.path("excludedIdentityTools").asLong()).isEqualTo(3);
    assertThat(json.path("measuredTools").asLong()).isEqualTo(1);
    assertThat(json.path("eligibleGroups").asLong()).isEqualTo(1);
    assertThat(json.path("candidates").get(0).path("subagentId").asText()).isEqualTo("B");
    assertThat(diagnostics.longOperations().measuredTools()).isEqualTo(3);
    assertThat(diagnostics.longOperations().unconfirmedIdentityTools()).isEqualTo(1);
  }

  @Test
  void workloadSignalsFindHiddenHundredSecondsAndKeepStableExactRepresentatives() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    var calls = new ArrayList<NormalizedCall>();
    tools.add(measured("spawn", "spawn_agent", null, "main", "", "", 0));
    for (int i = 1; i <= 11; i++) {
      String child = "child-" + String.format("%02d", i);
      calls.add(childCall(i, child));
      for (int j = 0; j < (i == 11 ? 200 : 1); j++)
        tools.add(
            owned(
                measured(
                    "exec-" + i + "-" + j,
                    "exec_command",
                    i == 9 ? 35_000_000_000L : 500_000_000L,
                    "subagent",
                    child,
                    "executor_reported",
                    j),
                "call-" + i));
    }
    tools.add(tools.getLast());
    var content = content(tools, calls);
    var diagnostics = SessionExecutionProjection.diagnostics(content);
    var json = new ObjectMapper().valueToTree(diagnostics).path("workloadSignals");
    assertThat(json.path("eligibleGroups").asLong()).isEqualTo(11);
    assertThat(json.path("candidates").size()).isEqualTo(3);
    assertThat(json.path("candidates").get(0).path("subagentId").asText()).isEqualTo("child-11");
    assertThat(json.path("candidates").get(0).path("measuredWorkNanos").asText())
        .isEqualTo("100000000000");
    assertThat(json.path("candidates").get(0).path("totalTools").asLong()).isEqualTo(200);
    assertThat(diagnostics.longOperations().candidates().getFirst().tool().subagentId())
        .isEqualTo("child-09");
    assertThat(
            new ObjectMapper()
                .valueToTree(
                    SessionExecutionProjection.diagnostics(content(tools.reversed(), calls)))
                .path("workloadSignals"))
        .isEqualTo(json);
    var selected =
        new ObjectMapper()
            .valueToTree(SessionExecutionProjection.diagnostics(content, "subagent:child-11"))
            .path("workloadSignals");
    assertThat(selected.path("totalTools").asLong()).isEqualTo(200);
    assertThat(selected.path("eligibleGroups").asLong()).isEqualTo(1);
  }

  @Test
  void workloadSignalsKeepZeroTinyHugeAndNonTypedCoverageDistinct() throws Exception {
    long huge = 9_000_000_000_000_000_001L;
    for (long nanos : List.of(0L, 1L, huge)) {
      var tools =
          List.of(
              measured("z", "exec_command", nanos, "main", "", "executor_reported", 1),
              measured("a", "exec_command", nanos, "main", "", "executor_reported", 2),
              measured("other", "exec_command", 5L, "main", "", "other_reported", 3),
              measured("source", "exec_command", 5L, "main", "", "executor_reported", -1),
              new NormalizedToolExecution(
                  "legacy",
                  "exec_command",
                  CallScope.MAIN,
                  "call-1",
                  Optional.empty(),
                  Optional.empty(),
                  Optional.empty(),
                  10L,
                  List.of(),
                  Optional.empty()),
              measured("anonymous", "exec_command", 100L, "subagent", "", "executor_reported", 4));
      var json =
          new ObjectMapper()
              .valueToTree(SessionExecutionProjection.diagnostics(content(tools)))
              .path("workloadSignals");
      // 匿名工具声明为 main，污染已知 main 组，不把缺身份调用猜为新组。
      assertThat(json.path("excludedIdentityTools").asLong()).isEqualTo(6);
      var valid =
          new ObjectMapper()
              .valueToTree(SessionExecutionProjection.diagnostics(content(tools.subList(0, 5))))
              .path("workloadSignals");
      assertThat(valid.path("totalTools").asLong()).isEqualTo(5);
      assertThat(valid.path("measuredTools").asLong()).isEqualTo(2);
      assertThat(valid.path("unknownTools").asLong()).isEqualTo(1);
      assertThat(valid.path("otherKindTools").asLong()).isEqualTo(2);
      assertThat(valid.path("candidates").get(0).path("measuredWorkNanos").asText())
          .isEqualTo(
              java.math.BigInteger.valueOf(nanos).multiply(java.math.BigInteger.TWO).toString());
      assertThat(
              valid
                  .path("candidates")
                  .get(0)
                  .path("longest")
                  .path("tool")
                  .path("toolCallId")
                  .asText())
          .isEqualTo("a");
    }
  }

  private static NormalizedToolExecution owned(NormalizedToolExecution tool, String owner) {
    return new NormalizedToolExecution(
        tool.toolCallId(),
        tool.name(),
        tool.scope(),
        owner,
        tool.resultConsumedByCallId(),
        tool.status(),
        tool.exitCode(),
        tool.durationMs(),
        tool.filesTouched(),
        tool.subagentId(),
        tool.observation());
  }

  private static NormalizedCall childCall(int index, String id) {
    var base = call(index, List.of(), List.of());
    return new NormalizedCall(
        base.callId(),
        index,
        base.callKey(),
        CallScope.SUBAGENT,
        Optional.empty(),
        Optional.of("spawn"),
        base.turnId(),
        base.model(),
        base.timestamp(),
        base.usage(),
        base.request(),
        base.response(),
        List.of(),
        base.sourceUnits(),
        Map.of(),
        Map.of(),
        Optional.of(id),
        Optional.of("spawn_agent"));
  }

  @Test
  void workloadSignalsAccumulatePartialTypedCoverageWithoutChangingSingleOperations()
      throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    for (int i = 0; i < 199; i++)
      tools.add(
          measured("short-" + i, "exec_command", 500_000_000L, "main", "", "executor_reported", i));
    tools.add(measured("unknown", "exec_command", null, "main", "", "", 200));
    tools.add(measured("wait", "wait", 200_000_000_000L, "main", "", "executor_reported", 201));
    var diagnostics = SessionExecutionProjection.diagnostics(content(tools));
    var json = new ObjectMapper().valueToTree(diagnostics).path("workloadSignals");
    assertThat(json.path("totalTools").asLong()).isEqualTo(200);
    assertThat(json.path("measuredTools").asLong()).isEqualTo(199);
    assertThat(json.path("unknownTools").asLong()).isEqualTo(1);
    assertThat(json.path("eligibleGroups").asLong()).isEqualTo(1);
    assertThat(json.path("candidates").get(0).path("measuredWorkNanos").asText())
        .isEqualTo("99500000000");
    assertThat(json.path("candidates").get(0).path("longest").path("durationNanos").asText())
        .isEqualTo("500000000");
    assertThat(diagnostics.longOperations().measuredTools()).isEqualTo(199);
  }

  @Test
  void confirmedChildrenBeyondEightGroupsRetainFullRangeAndAgentSelection() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    var calls = new ArrayList<NormalizedCall>();
    tools.add(measured("spawn", "spawn_agent", null, "main", "", "", 0));
    for (int i = 1; i <= 11; i++) {
      String id = "child-" + String.format("%02d", i);
      var original =
          measured(
              "exec-" + i,
              "exec_command",
              i == 9 ? 35_000_000_000L : 500_000L,
              "subagent",
              id,
              "executor_reported",
              i);
      tools.add(
          new NormalizedToolExecution(
              original.toolCallId(),
              original.name(),
              original.scope(),
              "call-" + i,
              original.resultConsumedByCallId(),
              original.status(),
              original.exitCode(),
              original.durationMs(),
              original.filesTouched(),
              original.subagentId(),
              original.observation()));
      var base = call(i, List.of(original.toolCallId()), List.of());
      calls.add(
          new NormalizedCall(
              base.callId(),
              i,
              base.callKey(),
              CallScope.SUBAGENT,
              Optional.empty(),
              Optional.of("spawn"),
              base.turnId(),
              base.model(),
              base.timestamp(),
              base.usage(),
              base.request(),
              base.response(),
              List.of(),
              base.sourceUnits(),
              Map.of(),
              Map.of(),
              Optional.of(id),
              Optional.of("spawn_agent")));
    }
    var content = content(tools, calls);
    var full = SessionExecutionProjection.diagnostics(content);
    assertThat(full.workloads()).hasSize(8);
    assertThat(full.workloadGroups()).isEqualTo(11);
    assertThat(full.longOperations().measuredTools()).isEqualTo(11);
    assertThat(full.longOperations().candidates().getFirst().tool().subagentId())
        .isEqualTo("child-09");
    assertThat(full.longOperations().candidates().getFirst().durationNanos())
        .isEqualTo("35000000000");
    assertThat(
            SessionExecutionProjection.diagnostics(content, "subagent:child-09")
                .longOperations()
                .totalTools())
        .isEqualTo(1);
    assertThat(
            SessionExecutionProjection.diagnostics(content, "subagent:child-10")
                .longOperations()
                .candidates()
                .getFirst()
                .tool()
                .toolCallId())
        .isEqualTo("exec-10");
    assertThat(
            SessionExecutionProjection.diagnostics(content, "subagent:missing")
                .longOperations()
                .candidates())
        .isEmpty();
    for (int invalid = 0; invalid < 5; invalid++) {
      var changed = new ArrayList<>(calls);
      var base = calls.get(8);
      changed.set(
          8,
          new NormalizedCall(
              base.callId(),
              base.callIndex(),
              base.callKey(),
              invalid == 0 ? CallScope.MAIN : CallScope.SUBAGENT,
              base.parentCallId(),
              invalid == 1
                  ? Optional.empty()
                  : invalid == 2 ? Optional.of("conflicting-unresolved") : base.parentToolCallId(),
              base.turnId(),
              base.model(),
              base.timestamp(),
              base.usage(),
              base.request(),
              base.response(),
              base.sourceUnitRefRanges(),
              base.sourceUnits(),
              base.attributionCandidates(),
              base.usageSource(),
              invalid == 4 ? Optional.of("different-instance") : base.subagentId(),
              invalid == 3 ? Optional.of("other_tool") : base.parentToolName()));
      var excluded =
          SessionExecutionProjection.diagnostics(content(tools, changed)).longOperations();
      assertThat(excluded.unconfirmedIdentityTools()).isEqualTo(1);
      assertThat(excluded.candidates())
          .noneMatch(value -> value.tool().toolCallId().equals("exec-9"));
    }
  }

  @Test
  void longSignalsUseExactNanosecondsAndStableIndependentToolIds() throws Exception {
    long huge = 9_000_000_000_000_000_000L;
    var tools =
        List.of(
            measured("lower", "exec_command", huge, "main", "", "executor_reported", 1),
            measured("tie-z", "exec_command", huge + 1, "main", "", "executor_reported", 2),
            measured("tie-a", "exec_command", huge + 1, "main", "", "executor_reported", 3));
    var original = SessionExecutionProjection.diagnostics(content(tools)).longOperations();
    assertThat(original.candidates())
        .extracting(value -> value.tool().toolCallId())
        .containsExactly("tie-a", "tie-z", "lower");
    assertThat(original.candidates().getFirst().durationNanos()).isEqualTo("9000000000000000001");
    assertThat(SessionExecutionProjection.diagnostics(content(tools.reversed())).longOperations())
        .isEqualTo(original);
  }

  @Test
  void longOperationSignalsExposeExactFullRangeFamilyWithoutWaitingTools() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    for (int i = 0; i < 11; i++)
      tools.add(measured("group-" + i, "name-" + i, 1L, "main", "", "executor_reported", i));
    tools.add(
        measured("long", "exec_command", 35_000_000_000L, "main", "", "executor_reported", 90));
    tools.add(measured("tiny", "exec_command", 1L, "main", "", "executor_reported", 91));
    tools.add(measured("zero", "exec_command", 0L, "main", "", "executor_reported", 92));
    tools.add(measured("wait", "wait", 90_000_000_000L, "main", "", "executor_reported", 93));
    tools.add(measured("unknown", "exec_command", null, "main", "", "", 94));
    tools.add(measured("other", "exec_command", 90_000_000_000L, "main", "", "other_reported", 95));
    tools.add(
        measured(
            "anonymous",
            "exec_command",
            90_000_000_000L,
            "subagent",
            "unknown-sidechain:x",
            "executor_reported",
            96));
    var json =
        new ObjectMapper().valueToTree(SessionExecutionProjection.diagnostics(content(tools)));
    var signals = json.path("longOperations");
    assertThat(signals.path("totalTools").asLong()).isEqualTo(6);
    assertThat(signals.path("measuredTools").asLong()).isEqualTo(3);
    assertThat(signals.path("unknownTools").asLong()).isEqualTo(1);
    assertThat(signals.path("otherKindTools").asLong()).isEqualTo(1);
    assertThat(signals.path("unconfirmedIdentityTools").asLong()).isEqualTo(1);
    assertThat(signals.path("candidates").findValuesAsText("toolCallId"))
        .contains("long", "tiny", "zero")
        .doesNotContain("wait", "anonymous");
    assertThat(signals.path("candidates").get(1).path("durationNanos").asText()).isEqualTo("1");
    assertThat(signals.path("candidates").get(2).path("durationNanos").asText()).isEqualTo("0");
  }

  @Test
  void slowCallsIncludeTheOffPageSecondScriptWithoutMergingIdenticalPreviews() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    tools.add(
        measured("build", "exec_command", 40_000_000_000L, "main", "", "executor_reported", 1));
    for (int i = 1; i <= 20; i++)
      tools.add(
          measured(
              "short-" + i, "exec_command", 50_000_000L, "main", "", "executor_reported", i + 1));
    tools.add(
        measured("test", "exec_command", 35_000_000_000L, "main", "", "executor_reported", 22));
    var first = SessionExecutionProjection.read(content(tools), "slow", null, 20, null, "all");
    assertThat(first.items()).hasSize(20);
    assertThat(first.items()).noneMatch(item -> "test".equals(item.tool().toolCallId()));
    var work = workloads(tools).get(0);
    assertThat(work.path("measuredWorkNanos").asText()).isEqualTo("76000000000");
    assertThat(work.path("measuredTools").asInt()).isEqualTo(22);
    assertThat(slowIds(work)).containsExactly("build", "test", "short-1");
    assertThat(work.path("slowest").findValuesAsText("inputPreview")).containsExactly("", "", "");
    assertThat(work.path("slowest").get(0)).isEqualTo(work.path("longest"));
    var repeated = new ArrayList<>(tools);
    repeated.add(tools.getFirst());
    assertThat(workloads(repeated)).isEqualTo(workloads(tools));
    var located = SessionExecutionProjection.read(content(tools), "slow", null, 20, "test", "all");
    assertThat(located.offset()).isEqualTo(21);
    assertThat(located.items().getFirst().tool().toolCallId()).isEqualTo("test");
  }

  @Test
  void slowCallsRetainExactOrderStableTiesAndMeasuredZeroButExcludeUnknowns() throws Exception {
    long huge = 9_000_000_000_000_000_000L;
    var tools =
        List.of(
            measured("lower", "exec_command", huge, "main", "", "executor_reported", 1),
            measured("tie-z", "exec_command", huge + 1, "main", "", "executor_reported", 2),
            measured("tie-a", "exec_command", huge + 1, "main", "", "executor_reported", 3),
            measured("zero", "zeros", 0L, "main", "", "executor_reported", 4),
            measured("unknown", "zeros", null, "main", "", "", 5));
    var groups = workloads(tools);
    assertThat(slowIds(groups.get(0))).containsExactly("tie-a", "tie-z", "lower");
    assertThat(slowIds(groups.get(1))).containsExactly("zero");
    assertThat(groups.get(1).path("slowest").get(0).path("durationMs").asLong()).isZero();
    assertThat(workloads(new ArrayList<>(tools.reversed()))).isEqualTo(groups);
  }

  @Test
  void cumulativeWorkShowsRepeatedCallsZeroAndUnknownAcrossTheCompleteRange() throws Exception {
    for (boolean partial : List.of(false, true)) {
      var tools = new ArrayList<NormalizedToolExecution>();
      tools.add(
          measured("long", "exec_command", 9_000_000_000L, "main", "", "executor_reported", 1));
      for (int i = 1; i <= 24; i++)
        tools.add(
            measured(
                "wait-" + i, "write_stdin", 500_000_000L, "main", "", "executor_reported", i + 1));
      if (partial) {
        tools.add(measured("zero", "write_stdin", 0L, "main", "", "executor_reported", 26));
        for (int i = 1; i <= 25; i++)
          tools.add(measured("unknown-" + i, "write_stdin", null, "main", "", "", 0));
      }
      var content = content(tools);
      assertThat(SessionExecutionProjection.read(content, "work", null, 20, null, "all").items())
          .hasSize(20);
      var groups = workloads(tools);
      assertThat(groups.size()).isEqualTo(2);
      var waits = groups.get(0);
      assertThat(waits.path("name").asText()).isEqualTo("write_stdin");
      assertThat(waits.path("measuredWorkNanos").asText()).isEqualTo("12000000000");
      assertThat(waits.path("longest").path("durationMs").asLong()).isEqualTo(500);
      assertThat(waits.path("measuredTools").asLong()).isEqualTo(partial ? 25 : 24);
      assertThat(waits.path("totalTools").asLong()).isEqualTo(partial ? 50 : 24);
      assertThat(waits.path("unknownTools").asLong()).isEqualTo(partial ? 25 : 0);
      assertThat(groups.get(1).path("longest").path("toolCallId").asText()).isEqualTo("long");
    }
  }

  @Test
  void eventLocatorsShareOneSupportedFamilyButUnknownKindsAndContextsNeverRankTogether()
      throws Exception {
    var tools =
        List.of(
            measured("main-a", "exec_command", 2L, "main", "", "executor_reported", 6),
            measured("main-b", "exec_command", 3L, "main", "", "executor_reported", 10),
            measured("other-kind", "exec_command", 100L, "main", "", "other_reported", 11),
            measured("unknown-kind", "exec_command", 100L, "main", "", "", 12),
            measured("unknown-source", "exec_command", 100L, "main", "", "executor_reported", -1),
            measured("unknown-time", "exec_command", null, "main", "", "", 0),
            measured(
                "child-a", "exec_command", 1_000L, "subagent", "child-A", "executor_reported", 13),
            measured(
                "child-b", "exec_command", 2_000L, "subagent", "child-B", "executor_reported", 14),
            measured(
                "unknown-child", "exec_command", 9_000L, "subagent", "", "executor_reported", 15));
    var groups = workloads(tools);
    assertThat(groups.size()).isEqualTo(3);
    var main = groups.get(0);
    assertThat(main.path("scope").asText()).isEqualTo("main");
    assertThat(main.path("measuredWorkNanos").asText()).isEqualTo("5");
    assertThat(main.path("totalTools").asLong()).isEqualTo(6);
    assertThat(main.path("otherKindTools").asLong()).isEqualTo(3);
    assertThat(main.path("unknownTools").asLong()).isEqualTo(1);
    assertThat(slowIds(main)).containsExactly("main-b", "main-a");
    assertThat(groups.get(1).path("subagentId").asText()).isEqualTo("child-A");
    assertThat(groups.get(2).path("subagentId").asText()).isEqualTo("child-B");
    assertThat(groups.get(1).path("measuredWorkNanos").asText()).isEqualTo("1000");
    assertThat(slowIds(groups.get(1))).containsExactly("child-a");
    assertThat(slowIds(groups.get(2))).containsExactly("child-b");
  }

  @Test
  void cumulativeOrderingIsExactBeyondLongAndDoublePrecisionAndRepresentativeTiesAreStable()
      throws Exception {
    long huge = 9_000_000_000_000_000_000L;
    var tools =
        List.of(
            measured("a-1", "alpha", huge, "main", "", "executor_reported", 1),
            measured("a-2", "alpha", huge, "main", "", "executor_reported", 2),
            measured("b-1", "beta", huge, "main", "", "executor_reported", 3),
            measured("b-2", "beta", huge + 1, "main", "", "executor_reported", 4),
            measured("tie-z", "ties", 500_000L, "main", "", "executor_reported", 5),
            measured("tie-a", "ties", 500_000L, "main", "", "executor_reported", 6));
    var groups = workloads(tools);
    assertThat(groups.get(0).path("name").asText()).isEqualTo("beta");
    assertThat(groups.get(0).path("measuredWorkNanos").asText()).isEqualTo("18000000000000000001");
    assertThat(groups.get(0).path("longest").path("toolCallId").asText()).isEqualTo("b-2");
    assertThat(groups.get(2).path("measuredWorkNanos").asText()).isEqualTo("1000000");
    assertThat(groups.get(2).path("longest").path("toolCallId").asText()).isEqualTo("tie-a");
    var reversed = new ArrayList<>(tools.reversed());
    assertThat(workloads(reversed)).isEqualTo(groups);
  }

  @Test
  void workloadOutputIsBoundedAndCountsDistinctIdsNotRepeatedRecords() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    for (int i = 1; i <= 12; i++)
      tools.add(measured("t-" + i, "name-" + i, (long) i, "main", "", "executor_reported", i));
    tools.add(tools.getFirst());
    var diagnostics =
        new ObjectMapper().valueToTree(SessionExecutionProjection.diagnostics(content(tools)));
    assertThat(diagnostics.path("totalTools").asLong()).isEqualTo(12);
    assertThat(diagnostics.path("workloadGroups").asLong()).isEqualTo(12);
    assertThat(diagnostics.path("workloads").size()).isEqualTo(8);
    assertThat(diagnostics.path("workloads").get(0).path("name").asText()).isEqualTo("name-12");
    assertThat(diagnostics.path("workloads").get(7).path("name").asText()).isEqualTo("name-5");
  }

  private static List<String> slowIds(JsonNode work) {
    var ids = new ArrayList<String>();
    work.path("slowest").forEach(tool -> ids.add(tool.path("toolCallId").asText()));
    return ids;
  }

  @Test
  void slowCandidatesStayWithinEightGroupsOfThreeIndependentCalls() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    for (int group = 0; group < 12; group++) {
      for (int call = 0; call < 4; call++)
        tools.add(
            measured(
                "g-" + group + "-" + call,
                "name-" + group,
                (long) call,
                "main",
                "",
                "executor_reported",
                group * 4 + call));
    }
    var groups = workloads(tools);
    assertThat(groups.size()).isEqualTo(8);
    for (var group : groups) {
      assertThat(group.path("slowest").size()).isEqualTo(3);
      assertThat(group.path("slowest").get(0)).isEqualTo(group.path("longest"));
    }
  }

  private static JsonNode workloads(List<NormalizedToolExecution> tools) throws Exception {
    return new ObjectMapper()
        .valueToTree(SessionExecutionProjection.diagnostics(content(tools)))
        .path("workloads");
  }

  private static NormalizedToolExecution measured(
      String id, String name, Long nanos, String scope, String child, String kind, int event) {
    var observed =
        nanos == null
            ? Optional.<SourceToolObservation>empty()
            : Optional.of(
                new SourceToolObservation(
                    id,
                    nanos,
                    null,
                    null,
                    null,
                    kind,
                    event < 0
                        ? "unrecognized:event"
                        : "codex:exec_command_end#event[" + event + "]",
                    null));
    return new NormalizedToolExecution(
        id,
        name,
        "main".equals(scope) ? CallScope.MAIN : CallScope.SUBAGENT,
        "call-1",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        nanos == null ? null : nanos / 1_000_000,
        List.of(),
        child.isEmpty() ? Optional.empty() : Optional.of(child),
        observed);
  }

  @Test
  void resultPresenceIncludesEmptyCatalogBodiesButNotConsumerOrExecutorEdges() throws Exception {
    var original = content(List.of(tool("empty", null, null), tool("missing", 0L, 0))).toArtifact();
    var entry =
        new com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry(
            "synthetic-result",
            "synthetic",
            "synthetic#event[1]",
            "text",
            "",
            com.feipi.session.browser.domain.normalized.SourceUnitDirection.REQUEST,
            1,
            0,
            com.feipi.session.browser.domain.normalized.ByteRange.empty(),
            "",
            Optional.empty(),
            Optional.of("empty"),
            50,
            Optional.empty(),
            Optional.of(""),
            Map.of("type", "tool_result", "tool_call_id", "empty"),
            Optional.empty(),
            Optional.empty(),
            List.of());
    var artifact =
        new com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact(
            original.schemaVersion(),
            original.agent(),
            original.sourceFiles(),
            original.session(),
            original.calls(),
            original.toolExecutions(),
            original.diagnostics(),
            Map.of(entry.unitKey(), entry),
            Map.of());
    var page =
        SessionExecutionProjection.read(
            NormalizedSessionContent.fromArtifact(artifact), "presence", null, 20, null, "all");
    assertThat(page.items().get(0).tool().resultObserved()).isTrue();
    assertThat(page.items().get(1).tool().resultObserved()).isFalse();
    assertThat(page.items().get(1).tool().durationMs()).isZero();
  }

  @Test
  void zeroSubmillisecondUnknownAndConsumedResultRemainDistinct() throws Exception {
    var tools =
        List.of(tool("zero", 0L, 0), tool("tiny", 500_000L, 7), tool("unknown", null, null));
    var content = content(tools);
    var first = SessionExecutionProjection.read(content, "scope-A", null, 1, null, "all");
    assertThat(first.total()).isEqualTo(4);
    assertThat(first.items()).hasSize(1);
    assertThat(first.items().getFirst().tool().durationMs()).isZero();
    assertThat(first.items().getFirst().group().inputAvailable()).isFalse();
    assertThat(first.items().getFirst().group().outputAvailable()).isTrue();
    assertThat(first.items().getFirst().tool().observation().status()).isNull();
    var second =
        SessionExecutionProjection.read(content, "scope-A", first.nextCursor(), 1, null, "all");
    assertThat(second.items().getFirst().group()).isEqualTo(first.items().getFirst().group());
    assertThat(second.items().getFirst().group().toolCount()).isEqualTo(3);
    assertThat(second.items().getFirst().tool().observation().durationNanos()).isEqualTo(500_000L);
    var located = SessionExecutionProjection.read(content, "scope-A", null, 1, "unknown", "all");
    assertThat(located.offset()).isEqualTo(2);
    assertThat(located.items().getFirst().tool().durationMs()).isNull();
    var diagnostics = SessionExecutionProjection.diagnostics(content);
    assertThat(diagnostics.totalTools()).isEqualTo(3);
    assertThat(diagnostics.measuredTools()).isEqualTo(2);
    assertThat(diagnostics.measuredWorkMs()).isEqualTo(0.5);
    assertThat(diagnostics.failures()).isEqualTo(1);
    assertThat(diagnostics.firstFailure()).isEqualTo("tiny");
    assertThat(diagnostics.firstFailureTool().toolCallId()).isEqualTo("tiny");
    assertThat(diagnostics.longestByName().getFirst().toolCallId()).isEqualTo("tiny");
    var failed = SessionExecutionProjection.read(content, "failed-A", null, 20, null, "failed");
    assertThat(failed.items()).hasSize(1);
    assertThat(failed.items().getFirst().tool().toolCallId()).isEqualTo("tiny");
    assertThatThrownBy(
            () ->
                SessionExecutionProjection.read(
                    content, "scope-B", first.nextCursor(), 1, null, "all"))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void longResponseHasBoundedActionsAndStableOwnerAcrossPages() throws Exception {
    var tools =
        IntStream.rangeClosed(1, 205).mapToObj(i -> tool("tool-" + i, (long) i, 0)).toList();
    var content = content(tools);
    var first = SessionExecutionProjection.read(content, "large", null, 100, null, "all");
    var second =
        SessionExecutionProjection.read(content, "large", first.nextCursor(), 100, null, "all");
    assertThat(first.items()).hasSize(100);
    assertThat(second.items()).hasSize(100);
    assertThat(second.items().getFirst().group()).isEqualTo(first.items().getFirst().group());
    assertThat(second.items().getFirst().tool().toolCallId()).isEqualTo("tool-101");
    assertThat(first.items().getFirst().group().toolCount()).isEqualTo(205);
    var tail = SessionExecutionProjection.read(content, "large", null, 20, "tool-205", "all");
    assertThat(tail.items()).hasSize(2);
    assertThat(tail.offset()).isEqualTo(204);
    assertThat(tail.nextCursor()).isNull();
  }

  @Test
  void sameNameWithDifferentMeasurementKindsDoesNotCompete() throws Exception {
    var content =
        content(List.of(tool("executor", 9L, 0), tool("other", 10L, 0, "other_reported")));
    var diagnostics = SessionExecutionProjection.diagnostics(content);
    assertThat(diagnostics.measuredKinds()).isEqualTo(2);
    assertThat(diagnostics.longestByName())
        .extracting(ApiResponses.ToolExecutionSummary::toolCallId)
        .containsExactlyInAnyOrder("executor", "other");
  }

  @Test
  void longestSelectionDoesNotLoseNanosecondsToFloatingPointComparison() throws Exception {
    var content =
        content(
            List.of(
                tool("shorter", 9_000_000_000_000_000_000L, 0),
                tool("longer", 9_000_000_000_000_000_001L, 0)));
    assertThat(
            SessionExecutionProjection.diagnostics(content).longestByName().getFirst().toolCallId())
        .isEqualTo("longer");
  }

  private static NormalizedSessionContent content(List<NormalizedToolExecution> tools) {
    var ids = tools.stream().map(NormalizedToolExecution::toolCallId).toList();
    var calls = List.of(call(1, ids, List.of()), call(2, List.of(), ids));
    return content(tools, calls);
  }

  private static NormalizedSessionContent content(
      List<NormalizedToolExecution> tools, List<NormalizedCall> calls) {
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                (long) calls.size(),
                "toolExecutions",
                (long) tools.size(),
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
        tools,
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(int index, List<String> declarations, List<String> results) {
    return new NormalizedCall(
        "call-" + index,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.of("same-turn"),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(0, 0, 0, 0, 0),
        new NormalizedCallRequest(results),
        new NormalizedCallResponse(declarations),
        List.of(),
        List.of(Map.of("role", "assistant", "type", "text", "text", "synthetic response " + index)),
        Map.of(),
        Map.of());
  }

  private static NormalizedToolExecution tool(String id, Long nanos, Integer exit) {
    return tool(id, nanos, exit, "executor_reported");
  }

  private static NormalizedToolExecution tool(String id, Long nanos, Integer exit, String kind) {
    var observation =
        nanos == null
            ? Optional.<SourceToolObservation>empty()
            : Optional.of(
                new SourceToolObservation(
                    id, nanos, exit, null, null, kind, "synthetic:end", null));
    return new NormalizedToolExecution(
        id,
        "exec_command",
        CallScope.MAIN,
        "call-1",
        Optional.of("call-2"),
        Optional.empty(),
        Optional.ofNullable(exit),
        nanos == null ? null : nanos / 1_000_000,
        List.of(),
        Optional.empty(),
        observation);
  }
}
