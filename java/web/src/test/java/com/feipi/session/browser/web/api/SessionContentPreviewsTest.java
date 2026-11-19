package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedCollaborationAction;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 同冻结内容的声明资格不由工具名称或结果猜测。 */
class SessionContentPreviewsTest {
  private static final String INPUT = "{\"message\":\"Synthetic followup <b>message</b>\"}";
  private static final String SUMMARY = "追加输入：Synthetic followup <b>message</b>";

  @Test
  void qualifiedInlineInputUsesSafeOperationText() throws Exception {
    var call = call("synthetic-tool", "send_input", INPUT);
    var tool = tool("synthetic-tool", "send_input", "input", "declaration", "explicit_target");
    assertThat(SessionContentPreviews.read(content(List.of(call), List.of(tool))).toolInputs(call))
        .containsEntry("synthetic-tool", SUMMARY);
  }

  @Test
  void bareNamesReceiptsUnknownAndConflictingFactsKeepGenericPreview() throws Exception {
    var call = call("synthetic-tool", "send_input", INPUT);
    for (var tools :
        List.of(
            List.<NormalizedToolExecution>of(),
            List.of(
                tool("synthetic-tool", "send_input", "input", "result_report", "explicit_target")),
            List.of(tool("synthetic-tool", "send_input", "wait", "declaration", "explicit_target")),
            List.of(
                tool(
                    "synthetic-tool",
                    "send_input",
                    "input",
                    "declaration",
                    "conflicting_tool_identity")),
            List.of(tool("synthetic-tool", "send_input", "input", "declaration", "target_unknown")),
            List.of(
                tool("synthetic-tool", "other_name", "input", "declaration", "explicit_target")))) {
      assertThat(SessionContentPreviews.read(content(List.of(call), tools)).toolInputs(call))
          .containsEntry("synthetic-tool", INPUT);
    }
    var tool = tool("synthetic-tool", "send_input", "input", "declaration", "explicit_target");
    var repeated =
        tool.withCollaboration(
            List.of(tool.collaboration().getFirst(), tool.collaboration().getFirst()));
    for (var tools : List.of(List.of(tool, tool), List.of(repeated))) {
      assertThat(SessionContentPreviews.read(content(List.of(call), tools)).toolInputs(call))
          .containsEntry("synthetic-tool", INPUT);
    }
    assertThat(
            SessionContentPreviews.read(content(List.of(call, call), List.of(tool)))
                .toolInputs(call))
        .containsEntry("synthetic-tool", INPUT);
  }

  @Test
  void mismatchedActorScopeCallAndUnrecordedCallsNeverUpgrade() throws Exception {
    var call = call("synthetic-tool", "send_input", INPUT);
    var tool = tool("synthetic-tool", "send_input", "input", "declaration", "explicit_target");
    var action = tool.collaboration().getFirst();
    for (String reason : List.of("actor_unknown", "anonymous_sidechain", "explicit_instance")) {
      var wrongActor =
          tool.withCollaboration(
              List.of(
                  new NormalizedCollaborationAction(
                      action.kind(),
                      action.phase(),
                      Optional.of("synthetic-other"),
                      action.targetId(),
                      action.sourceLocator(),
                      action.reportedStatus(),
                      action.reason(),
                      reason)));
      assertThat(
              SessionContentPreviews.read(content(List.of(call), List.of(wrongActor)))
                  .toolInputs(call))
          .containsEntry("synthetic-tool", INPUT);
    }
    var child = scoped(call, "child-call", "synthetic-child");
    assertThat(
            SessionContentPreviews.read(content(List.of(child), List.of(tool))).toolInputs(child))
        .containsEntry("synthetic-tool", INPUT);
    assertThat(SessionContentPreviews.read(content(List.of(), List.of(tool))).toolInputs(call))
        .containsEntry("synthetic-tool", INPUT);
    assertThat(
            SessionContentPreviews.read(content(List.of(call, child), List.of(tool)))
                .toolInputs(call))
        .containsEntry("synthetic-tool", INPUT);
  }

  @Test
  void catalogAndInlineUseTheSamePolicyRegardlessOfFactOrderWithoutExtraCursor() throws Exception {
    var inline = call("synthetic-tool", "send_input", INPUT);
    var tool = tool("synthetic-tool", "send_input", "input", "declaration", "explicit_target");
    var entry = catalog("synthetic-catalog", inline.sourceUnits().getFirst());
    for (boolean catalogFirst : List.of(true, false)) {
      for (boolean includeInline : List.of(true, false)) {
        var call = includeInline ? inline : withoutInline(inline);
        var catalogUnit = unit(0, List.of(), List.of(), Map.of(entry.unitKey(), entry));
        var callUnit = unit(1, List.of(call), List.of(), Map.of());
        var toolUnit = unit(2, List.of(), List.of(tool), Map.of());
        var units =
            catalogFirst
                ? List.of(catalogUnit, callUnit, toolUnit)
                : List.of(toolUnit, callUnit, catalogUnit);
        var opens = new int[] {0};
        var frozen = streamed(units, opens);
        assertThat(SessionContentPreviews.read(frozen).toolInputs(call))
            .containsEntry("synthetic-tool", SUMMARY);
        assertThat(opens[0]).isEqualTo(1);
      }
    }
  }

  @Test
  void inconsistentInputsWithIdenticalTruncatedPrefixesDoNotChooseFirstOrLast() throws Exception {
    String first = "{\"message\":\"" + "x".repeat(250) + "first\"}";
    String second = "{\"message\":\"" + "x".repeat(250) + "second\"}";
    var call = call("synthetic-tool", "send_input", first);
    var other = call("synthetic-tool", "send_input", second);
    var tool = tool("synthetic-tool", "send_input", "input", "declaration", "explicit_target");
    var entry = catalog("synthetic-catalog", other.sourceUnits().getFirst());
    var frozen =
        streamed(
            List.of(unit(0, List.of(call), List.of(tool), Map.of(entry.unitKey(), entry))),
            new int[] {0});
    assertThat(SessionContentPreviews.read(frozen).toolInputs(call))
        .containsEntry(
            "synthetic-tool",
            ToolInputPreview.from(
                new ToolInputContents.Input("synthetic-tool", "send_input", second)));
  }

  @Test
  void distinctNormalizedOccurrencesAndFrozenImportsCannotShareQualification() throws Exception {
    var first = call("normalized-tool:1:0", "send_input", INPUT);
    var second = call("normalized-tool:2:0", "send_input", INPUT);
    var qualified =
        tool("normalized-tool:1:0", "send_input", "input", "declaration", "explicit_target");
    assertThat(
            SessionContentPreviews.read(content(List.of(first), List.of(qualified)))
                .toolInputs(first))
        .containsEntry("normalized-tool:1:0", SUMMARY);
    assertThat(
            SessionContentPreviews.read(content(List.of(second), List.of(qualified)))
                .toolInputs(second))
        .containsEntry("normalized-tool:2:0", INPUT);
    assertThat(SessionContentPreviews.read(content(List.of(first), List.of())).toolInputs(first))
        .containsEntry("normalized-tool:1:0", INPUT);
  }

  @Test
  void typedClaudeDelegateAllowsPromptWithoutInventingTargetIdentity() throws Exception {
    var call = call("synthetic-tool", "Agent", "{\"prompt\":\"Synthetic task\"}");
    var tool = tool("synthetic-tool", "Agent", "delegate", "declaration", "target_unknown");
    var action = tool.collaboration().getFirst();
    tool =
        tool.withCollaboration(
            List.of(
                new NormalizedCollaborationAction(
                    action.kind(),
                    action.phase(),
                    action.actorId(),
                    Optional.empty(),
                    action.sourceLocator(),
                    action.reportedStatus(),
                    action.reason(),
                    action.actorIdentityReason())));
    assertThat(SessionContentPreviews.read(content(List.of(call), List.of(tool))).toolInputs(call))
        .containsEntry("synthetic-tool", "委派任务：Synthetic task");
  }

  @Test
  void delegateAssociatedChildIsNotTheCallerAndImportDoesNotEraseProtocolQualification()
      throws Exception {
    var call = call("synthetic-tool", "spawn_agent", "{\"message\":\"Synthetic task\"}");
    for (String reason :
        List.of("child_candidate_available", "child_not_found", "single_file_not_included")) {
      var tool = tool("synthetic-tool", "spawn_agent", "delegate", "declaration", reason);
      var associated = associated(tool, "synthetic-child");
      assertThat(
              SessionContentPreviews.read(content(List.of(call), List.of(associated)))
                  .toolInputs(call))
          .containsEntry("synthetic-tool", "委派任务：Synthetic task");
      assertThat(
              SessionContentPreviews.read(
                      content(List.of(call), List.of(associated(tool, "synthetic-other"))))
                  .toolInputs(call))
          .containsEntry("synthetic-tool", "{\"message\":\"Synthetic task\"}");
    }
    var input = call("synthetic-tool", "send_input", INPUT);
    var inputTool = tool("synthetic-tool", "send_input", "input", "declaration", "explicit_target");
    assertThat(
            SessionContentPreviews.read(
                    content(List.of(input), List.of(associated(inputTool, "synthetic-child"))))
                .toolInputs(input))
        .containsEntry("synthetic-tool", INPUT);
    var importReason =
        tool("synthetic-tool", "send_input", "input", "declaration", "single_file_not_included");
    assertThat(
            SessionContentPreviews.read(content(List.of(input), List.of(importReason)))
                .toolInputs(input))
        .containsEntry("synthetic-tool", INPUT);
  }

  private static NormalizedToolExecution associated(NormalizedToolExecution tool, String child) {
    return new NormalizedToolExecution(
        tool.toolCallId(),
        tool.name(),
        tool.scope(),
        tool.declaredByCallId(),
        tool.resultConsumedByCallId(),
        tool.status(),
        tool.exitCode(),
        tool.durationMs(),
        tool.filesTouched(),
        Optional.of(child),
        tool.observation(),
        tool.collaboration());
  }

  private static NormalizedCall call(String id, String name, String input) {
    return new NormalizedCall(
        "synthetic-call",
        1,
        "C1",
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(0, 0, 0, 0, 0),
        new NormalizedCallRequest(List.of()),
        new NormalizedCallResponse(List.of(id)),
        List.of(),
        List.of(Map.of("type", "function_call", "call_id", id, "name", name, "arguments", input)),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall scoped(NormalizedCall call, String callId, String actor) {
    return new NormalizedCall(
        callId,
        2,
        "C2",
        CallScope.SUBAGENT,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        call.usage(),
        call.request(),
        call.response(),
        List.of(),
        call.sourceUnits(),
        Map.of(),
        Map.of(),
        Optional.of(actor),
        Optional.empty());
  }

  private static NormalizedCall withoutInline(NormalizedCall call) {
    return new NormalizedCall(
        call.callId(),
        call.callIndex(),
        call.callKey(),
        call.scope(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        call.usage(),
        call.request(),
        call.response(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedToolExecution tool(
      String id, String name, String kind, String phase, String reason) {
    return new NormalizedToolExecution(
        id,
        name,
        CallScope.MAIN,
        "synthetic-call",
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        (Long) null,
        List.of(),
        Optional.empty(),
        Optional.empty(),
        List.of(
            new NormalizedCollaborationAction(
                kind,
                phase,
                Optional.empty(),
                Optional.of("synthetic-child"),
                "synthetic:event",
                Optional.empty(),
                reason,
                "main_context")));
  }

  private static SourceUnitCatalogEntry catalog(String key, Object payload) {
    return new SourceUnitCatalogEntry(
        key,
        "synthetic.jsonl",
        "synthetic:event",
        "function_call",
        "response",
        SourceUnitDirection.RESPONSE,
        0,
        0,
        new ByteRange(0, 0),
        "synthetic",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.empty(),
        payload,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  private static NormalizedContentUnit unit(
      long index,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog) {
    return new NormalizedContentUnit(index, List.of(), calls, tools, List.of(), catalog, List.of());
  }

  private static NormalizedSessionContent streamed(List<NormalizedContentUnit> units, int[] opens) {
    return new NormalizedSessionContent() {
      @Override
      public NormalizedContentHeader header() {
        return content(List.of(), List.of()).header();
      }

      @Override
      public ContentCursor openCursor() {
        opens[0]++;
        var iterator = units.iterator();
        return new ContentCursor() {
          @Override
          public boolean hasNext() {
            return iterator.hasNext();
          }

          @Override
          public NormalizedContentUnit next() {
            return iterator.next();
          }

          @Override
          public void close() {}
        };
      }
    };
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
}
