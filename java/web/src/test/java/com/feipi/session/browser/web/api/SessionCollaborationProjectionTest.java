package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedCollaborationAction;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 紧凑事实投影的身份、两层边界及选择隔离；真源保真由 HTTP 场景承接。 */
class SessionCollaborationProjectionTest {
  @Test
  void lateNestedReportCandidatesRetainEarlierToolConflicts() throws Exception {
    var calls = List.of(call(1, "", List.of("spawn", "report")));
    // 同ID的早期工具不指向本页目标；enrich 到后面的 report 才收集该候选。
    var tools =
        List.of(
            tool("report", 1, "other", "wait", "result_report"),
            tool("spawn", 1, "child", "delegate", "declaration"),
            tool("report", 1, "child", "wait", "result_report"));
    var content = content(calls, tools);
    var protectedPage =
        SessionCollaborationProjection.read(
            content,
            "protected",
            SessionContentCursor.encode("protected", 1),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    var main = protectedPage.items().getFirst();
    assertThat(main).containsEntry("toolId", "spawn").containsEntry("toolPayloadState", "unique");
    assertThat(main.get("reports")).isInstanceOf(List.class);
    var reports = (List<?>) main.get("reports");
    assertThat(reports).hasSize(1);
    assertThat(reports.getFirst())
        .isEqualTo(
            Map.of(
                "toolId",
                "report",
                "callId",
                "call-1",
                "callIndex",
                1,
                "kind",
                "wait",
                "phase",
                "result_report",
                "reportedStatus",
                "",
                "toolPayloadState",
                "ambiguous"));
    var ordinaryPage =
        SessionCollaborationProjection.read(
            content, "ordinary", SessionContentCursor.encode("ordinary", 1), 20, "", "exchanges");
    assertThat(ordinaryPage.items())
        .allSatisfy(row -> assertThat(row).doesNotContainKey("toolPayloadState"));
    var ordinaryReports = (List<?>) ordinaryPage.items().getFirst().get("reports");
    assertThat(ordinaryReports).hasSize(1);
    assertThat(((Map<?, ?>) ordinaryReports.getFirst()).containsKey("toolPayloadState")).isFalse();
    for (String total : List.of("calls", "toolExecutions")) {
      var totals = new java.util.LinkedHashMap<>(content.header().totals());
      totals.compute(total, (key, value) -> value + 1);
      var header =
          new NormalizedContentHeader(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CODEX,
              new NormalizedSessionMetadata(Map.of()),
              totals);
      var incomplete = content.withHeader(header);
      var incompletePage =
          SessionCollaborationProjection.read(
              incomplete,
              "protected",
              SessionContentCursor.encode("protected", 1),
              20,
              "",
              "exchanges",
              new SessionCollaborationProjection.EvidenceWindow(
                  "protected", "input_submission_error"));
      assertThat(incompletePage.items().getFirst())
          .containsEntry("toolId", "spawn")
          .containsEntry("toolPayloadState", "unconfirmed");
    }
  }

  @Test
  void explicitInputErrorsHaveCanonicalGlobalReference() throws Exception {
    var base = tool("error", 1, "missing", "input", "result_report");
    var action = base.collaboration().getFirst();
    var error =
        new NormalizedToolExecution(
            base.toolCallId(),
            base.name(),
            CallScope.MAIN,
            base.declaredByCallId(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            null,
            List.of(),
            base.subagentId(),
            Optional.empty(),
            List.of(
                new NormalizedCollaborationAction(
                    "input",
                    "result_report",
                    Optional.empty(),
                    action.targetId(),
                    "synthetic#error",
                    Optional.empty(),
                    "explicit_error",
                    "main_context")));
    var tools = new ArrayList<NormalizedToolExecution>();
    for (int i = 0; i < 25; i++)
      tools.add(tool("prefix-" + i, 1, "missing", "input", "declaration"));
    tools.add(error);
    tools.add(error);
    var content = content(List.of(call(1, "", List.of("error"))), tools);
    var page =
        SessionCollaborationProjection.read(content, "ordinary", null, 1, "", "participants");
    assertThat(page.inputSubmissionErrorReportTotal()).isEqualTo(2);
    assertThat(page.firstInputSubmissionError().exchangeOffset()).isEqualTo(25);
    var protectedPage =
        SessionCollaborationProjection.read(
            content,
            "protected",
            SessionContentCursor.encode("protected", 25),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    assertThat(protectedPage.offset()).isEqualTo(25);
    assertThat(protectedPage.evidenceWindow()).isEqualTo("input_submission_error");
    assertThat(protectedPage.items())
        .allSatisfy(
            row ->
                assertThat(row)
                    .containsEntry("reason", "explicit_error")
                    .containsEntry("toolPayloadState", "ambiguous"));
    var unique = content(List.of(call(1, "", List.of("error"))), List.of(error));
    var uniquePage =
        SessionCollaborationProjection.read(
            unique,
            "protected",
            SessionContentCursor.encode("protected", 0),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    assertThat(uniquePage.items().getFirst()).containsEntry("toolPayloadState", "unique");
    var duplicateCall =
        content(List.of(call(1, "", List.of()), call(1, "other", List.of())), List.of(error));
    var conflicting =
        SessionCollaborationProjection.read(
            duplicateCall,
            "protected",
            SessionContentCursor.encode("protected", 0),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    assertThat(conflicting.items().getFirst()).containsEntry("toolPayloadState", "ambiguous");
    var unknownOwner =
        SessionCollaborationProjection.read(
            content(List.of(), List.of(error)),
            "protected",
            SessionContentCursor.encode("protected", 0),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    assertThat(unknownOwner.items().getFirst()).containsEntry("toolPayloadState", "unique");
    var repeatedDeclaration =
        SessionCollaborationProjection.read(
            content(List.of(call(1, "", List.of("error", "error"))), List.of(error)),
            "protected",
            SessionContentCursor.encode("protected", 0),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    assertThat(repeatedDeclaration.items().getFirst())
        .containsEntry("toolPayloadState", "ambiguous");
    for (String view : List.of("participants", "exchanges", "delegations")) {
      var summary =
          SessionCollaborationProjection.read(
              content,
              "ordinary",
              null,
              1,
              "main",
              view,
              new SessionCollaborationProjection.EvidenceWindow("protected", ""));
      assertThat(summary.inputSubmissionErrorReportTotal()).isEqualTo(2);
      assertThat(summary.firstInputSubmissionError().exchangeOffset()).isEqualTo(25);
      assertThat(
              SessionContentCursor.decode(
                  summary.firstInputSubmissionError().cursor(), "protected"))
          .isEqualTo(25);
      assertThatThrownBy(
              () ->
                  SessionContentCursor.decode(
                      summary.firstInputSubmissionError().cursor(), "ordinary"))
          .isInstanceOf(IllegalArgumentException.class);
    }
    var manyErrors = new ArrayList<NormalizedToolExecution>();
    for (int i = 0; i < 24; i++) manyErrors.add(error);
    var manyContent = content(List.of(), manyErrors);
    var firstProtected =
        SessionCollaborationProjection.read(
            manyContent,
            "protected",
            SessionContentCursor.encode("protected", 0),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    var continuation =
        SessionCollaborationProjection.read(
            manyContent,
            "protected",
            firstProtected.nextCursor(),
            20,
            "",
            "exchanges",
            new SessionCollaborationProjection.EvidenceWindow(
                "protected", "input_submission_error"));
    assertThat(continuation.offset()).isEqualTo(20);
    assertThat(continuation.inputSubmissionErrorReportTotal()).isEqualTo(24);
    assertThat(continuation.evidenceWindow()).isEqualTo("input_submission_error");
    assertThat(continuation.items())
        .hasSize(4)
        .allSatisfy(row -> assertThat(row).containsEntry("toolPayloadState", "ambiguous"));
    assertThat(page.items())
        .allSatisfy(row -> assertThat(row).doesNotContainKey("toolPayloadState"));
  }

  @Test
  void executionOnlyParticipantsAppendAfterCanonicalTargetsWithoutCreatingRelations()
      throws Exception {
    var execution =
        new NormalizedToolExecution(
            "execution-only",
            "exec_command",
            CallScope.SUBAGENT,
            "unknown",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            null,
            List.of(),
            Optional.of("execution-child"),
            Optional.empty());
    var content =
        content(
            List.of(call(1, "violet", List.of("spawn")), call(2, "", List.of())),
            List.of(execution, tool("spawn", 1, "target-child", "delegate", "declaration")));
    var page =
        SessionCollaborationProjection.read(
            content, "canonical-execution", null, 20, "", "participants");
    assertThat(page.items())
        .extracting(row -> row.get("key"))
        .containsExactly(
            "subagent:violet", "main", "subagent:target-child", "subagent:execution-child");
    assertThat(page.items())
        .extracting(row -> row.get("label"))
        .containsExactly("Agent 0", "主 Agent", "Agent 2", "Agent 3");
    assertThat(page.items().get(2)).containsEntry("included", false);
    assertThat(page.items().get(3)).containsEntry("included", true);
    assertThat(page.delegationTotal()).isEqualTo(1);
    assertThat(page.exchangeTotal()).isEqualTo(1);
  }

  @Test
  void mainTargetDoesNotGainProcessAndUnconfirmedActionActorRemainsAnonymous() throws Exception {
    var anonymous = tool("unowned-spawn", 99, "absent-child", "delegate", "declaration");
    var content = content(List.of(call(1, "", List.of())), List.of(anonymous));
    var page =
        SessionCollaborationProjection.read(content, "unknown-action", null, 20, "", "delegations");
    assertThat(page.items().getFirst())
        .containsEntry("actor", "main")
        .containsEntry("childIncluded", false);
    var unresolved =
        new NormalizedToolExecution(
            "unresolved",
            "spawn_agent",
            CallScope.SUBAGENT,
            "unknown",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            null,
            List.of(),
            Optional.empty(),
            Optional.empty(),
            anonymous.collaboration());
    var unknown =
        SessionCollaborationProjection.read(
            content(List.of(), List.of(unresolved)), "unknown", null, 20, "", "delegations");
    assertThat(unknown.items().getFirst()).containsEntry("actor", "unknown:unknown");
    assertThat(unknown.participants())
        .anySatisfy(
            row ->
                assertThat(row)
                    .containsEntry("key", "unknown:unknown")
                    .containsEntry("included", false));
  }

  @Test
  void toolOnlyChildHasIncludedProcessWithoutInventingAnAnonymousActor() throws Exception {
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
            Optional.empty());
    var content =
        content(
            List.of(call(1, "", List.of("spawn"))),
            List.of(tool("spawn", 1, "synthetic-child", "delegate", "declaration"), child));
    var relations =
        SessionCollaborationProjection.read(content, "tool-only", null, 20, "", "delegations");
    assertThat(relations.items()).hasSize(1);
    assertThat(relations.items().getFirst())
        .containsEntry("actor", "main")
        .containsEntry("target", "subagent:synthetic-child")
        .containsEntry("actorLabel", "主 Agent")
        .containsEntry("targetLabel", "Agent 1");
    var participants =
        SessionCollaborationProjection.read(content, "tool-only", null, 20, "", "participants");
    org.assertj.core.api.SoftAssertions.assertSoftly(
        softly -> {
          softly.assertThat(relations.items().getFirst()).containsEntry("childIncluded", true);
          softly.assertThat(participants.participantTotal()).isEqualTo(2);
          softly
              .assertThat(participants.items())
              .extracting(row -> row.get("key"))
              .containsExactly("main", "subagent:synthetic-child");
          softly
              .assertThat(participants.items().get(1))
              .containsEntry("label", "Agent 1")
              .containsEntry("included", true);
        });
  }

  @Test
  void canonicalCallPrefixKeepsMainPositionAndToolOnlyTargetsAppendAfterIt() throws Exception {
    var content =
        content(
            List.of(
                call(1, "violet", List.of("spawn")),
                call(2, "", List.of()),
                call(3, "yarrow", List.of()),
                call(4, "violet", List.of())),
            List.of(tool("spawn", 1, "target-without-call", "delegate", "declaration")));
    var page =
        SessionCollaborationProjection.read(content, "prefix", null, 100, "", "participants");
    assertThat(page.items())
        .extracting(row -> row.get("key"))
        .containsExactly(
            "subagent:violet", "main", "subagent:yarrow", "subagent:target-without-call");
    assertThat(page.items())
        .extracting(row -> row.get("label"))
        .containsExactly("Agent 0", "主 Agent", "Agent 2", "Agent 3");
    var selected =
        SessionCollaborationProjection.read(
            content, "selected-prefix", null, 1, "subagent:violet", "delegations");
    assertThat(selected.items().getFirst())
        .containsEntry("actorLabel", "Agent 0")
        .containsEntry("targetLabel", "Agent 3");
    var execution =
        SessionExecutionProjection.read(
            content, "target-only", null, 1, null, "all", "subagent:violet");
    assertThat(execution.contextLabels())
        .containsExactlyInAnyOrderEntriesOf(
            Map.of("subagent:violet", "Agent 0", "main", "主 Agent"));
  }

  @Test
  void inputDeclarationCountsAreGlobalWithoutCreationEdgesOrPairedReports() throws Exception {
    var tools =
        List.of(
            tool("spawn", 1, "worker", "delegate", "declaration"),
            tool("input", 1, "worker", "input", "declaration"),
            tool("receipt", 1, "worker", "input", "result_report"),
            tool("missing-child", 1, "uncollected", "input", "declaration"));
    var content =
        content(
            List.of(
                call(1, "", List.of("spawn", "input", "receipt", "missing-child")),
                call(2, "worker", List.of())),
            tools);
    var creation =
        SessionCollaborationProjection.read(content, "creation", null, 1, "", "delegations");
    assertThat(creation.inputDeclarationTotal()).isEqualTo(2);
    assertThat(creation.delegationTotal()).isEqualTo(1);
    assertThat(creation.participantTotal()).isEqualTo(2);
    assertThat(creation.items().getFirst()).containsEntry("reportTotal", 0L);
    var first = SessionCollaborationProjection.read(content, "exchanges", null, 1, "", "exchanges");
    var next =
        SessionCollaborationProjection.read(
            content, "exchanges", first.nextCursor(), 1, "", "exchanges");
    assertThat(first.inputDeclarationTotal()).isEqualTo(2);
    assertThat(next.inputDeclarationTotal()).isEqualTo(2);
    assertThat(next.items().getFirst())
        .containsEntry("kind", "input")
        .containsEntry("reportTotal", 0L)
        .containsEntry("actor", "main");
    assertThat(next.items().getFirst().get("task").toString()).startsWith("追加内容摘要未安全解析");
    var selected =
        SessionCollaborationProjection.read(
            content, "selected", null, 1, "subagent:worker", "exchanges");
    assertThat(selected.inputDeclarationTotal()).isEqualTo(2);
    assertThat(selected.total()).isEqualTo(3);
    var participants =
        SessionCollaborationProjection.read(content, "participants", null, 1, "", "participants");
    assertThat(participants.inputDeclarationTotal()).isEqualTo(2);
  }

  @Test
  void nestedSiblingsFullIdentityTailReportsAndBackendAgentSelectionRemainDistinct()
      throws Exception {
    var calls =
        List.of(
            call(1, "", List.of("root-spawn", "wait")),
            call(2, "worker-prefix-001", List.of("child-spawn")),
            call(3, "worker-prefix-002", List.of()));
    var tools =
        List.of(
            tool("root-spawn", 1, "worker-prefix-001", "delegate", "declaration"),
            tool("child-spawn", 2, "worker-prefix-002", "delegate", "declaration"),
            tool("wait", 1, "worker-prefix-002", "wait", "result_report"));
    var content = content(calls, tools);
    var page = SessionCollaborationProjection.read(content, "root", null, 5, "", "delegations");
    assertThat(page.items()).hasSize(2);
    assertThat(page.items().getFirst())
        .containsEntry("actor", "main")
        .containsEntry("childIncluded", true);
    assertThat(page.items().get(1))
        .containsEntry("actor", "subagent:worker-prefix-001")
        .containsEntry("target", "subagent:worker-prefix-002")
        .containsEntry("depth", 1);
    assertThat(page.items().get(1).get("reportTotal")).isEqualTo(1L);
    assertThat(page.participantTotal()).isEqualTo(3);
    var selected =
        SessionExecutionProjection.read(
            content, "selected", null, 20, null, "all", "subagent:worker-prefix-001");
    assertThat(selected.items()).hasSize(1);
    assertThat(selected.items().getFirst().tool().toolCallId()).isEqualTo("child-spawn");
    assertThat(
            SessionExecutionProjection.diagnostics(content, "subagent:worker-prefix-001")
                .totalTools())
        .isEqualTo(1);
    assertThatThrownBy(
            () ->
                SessionExecutionProjection.read(
                    content,
                    "selected",
                    null,
                    20,
                    "root-spawn",
                    "all",
                    "subagent:worker-prefix-001"))
        .isInstanceOf(io.javalin.http.BadRequestResponse.class);
  }

  @Test
  void largeFactSetKeepsResponseWindowsAndParsingBudgetIndependentOfTotal() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    for (int i = 0; i < 1200; i++)
      tools.add(tool("spawn-" + i, 1, "worker-" + i, "delegate", "declaration"));
    var content =
        content(
            List.of(call(1, "", tools.stream().map(NormalizedToolExecution::toolCallId).toList())),
            tools);
    long started = System.nanoTime();
    var first = SessionCollaborationProjection.read(content, "scope-a", null, 5, "", "delegations");
    System.out.println(
        "collaboration compact benchmark: facts=1200, retainedPage="
            + first.items().size()
            + ", participants="
            + first.participants().size()
            + ", elapsedNanos="
            + (System.nanoTime() - started));
    assertThat(first.items()).hasSize(5);
    assertThat(first.participants()).hasSize(5);
    assertThat(first.total()).isEqualTo(1200);
    assertThat(first.participantTotal()).isEqualTo(1201);
    var next =
        SessionCollaborationProjection.read(
            content, "scope-a", first.nextCursor(), 5, "", "delegations");
    assertThat(next.items().getFirst()).containsEntry("toolId", "spawn-5");
    assertThatThrownBy(
            () ->
                SessionCollaborationProjection.read(
                    content, "scope-b", first.nextCursor(), 5, "", "delegations"))
        .isInstanceOf(IllegalArgumentException.class);
    var preview = new CollaborationTaskPreview(java.util.Set.of("t"));
    preview.observe(
        Map.of(
            "type",
            "function_call",
            "call_id",
            "t",
            "arguments",
            "{\"message\":\"" + "x".repeat(70_000) + "\"}"));
    assertThat(preview.get("t")).contains("未安全解析");
    preview.observe(
        Map.of(
            "type",
            "function_call",
            "call_id",
            "t",
            "arguments",
            "{\"message\":\"synthetic bounded task\"}"));
    assertThat(preview.get("t")).isEqualTo("synthetic bounded task");
  }

  @Test
  void deepBranchesAndConflictingParentsNeverInventATreeParent() throws Exception {
    var calls =
        List.of(
            call(1, "", List.of("a", "b")),
            call(2, "a", List.of("c")),
            call(3, "b", List.of("d")),
            call(4, "c", List.of("e")));
    var tools =
        List.of(
            tool("a", 1, "a", "delegate", "declaration"),
            tool("b", 1, "b", "delegate", "declaration"),
            tool("c", 2, "c", "delegate", "declaration"),
            tool("d", 3, "c", "delegate", "declaration"),
            tool("e", 4, "deep", "delegate", "declaration"));
    var page =
        SessionCollaborationProjection.read(content(calls, tools), "s", null, 5, "", "delegations");
    assertThat(page.items())
        .filteredOn(row -> "subagent:c".equals(row.get("target")))
        .allSatisfy(row -> assertThat(row.get("parentIssue")).isEqualTo("multiple_parents"));
  }

  private static NormalizedSessionContent content(
      List<NormalizedCall> calls, List<NormalizedToolExecution> tools) {
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

  private static NormalizedCall call(int index, String agent, List<String> tools) {
    return new NormalizedCall(
        "call-" + index,
        index,
        "C" + index,
        agent.isEmpty() ? CallScope.MAIN : CallScope.SUBAGENT,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(0, 0, 0, 0, 0),
        new NormalizedCallRequest(List.of()),
        new NormalizedCallResponse(tools),
        List.of(),
        List.of(),
        Map.of(),
        Map.of(),
        Optional.ofNullable(agent.isEmpty() ? null : agent),
        Optional.empty());
  }

  private static NormalizedToolExecution tool(
      String id, int owner, String target, String kind, String phase) {
    return new NormalizedToolExecution(
        id,
        kind.equals("wait") ? "wait_agent" : "spawn_agent",
        CallScope.MAIN,
        "call-" + owner,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        null,
        List.of(),
        Optional.of(target),
        Optional.empty(),
        List.of(
            new NormalizedCollaborationAction(
                kind,
                phase,
                Optional.empty(),
                Optional.of(target),
                "synthetic#" + id,
                Optional.empty(),
                "child_candidate_available",
                "main_context")));
  }
}
