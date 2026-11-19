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
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 权威编号只由完整调用前缀决定；响应只携真实引用的交集。 */
class SessionContextLabelsTest {
  @Test
  void nonNumericReorderedAnonymousAndRepeatedCallsMatchCanonicalParticipants() throws Exception {
    var calls =
        List.of(
            call(1, null),
            call(2, "violet"),
            call(3, ""),
            call(4, "unknown-sidechain:synthetic"),
            call(5, "yarrow"),
            call(6, "violet"));
    var content = content(calls);
    var canonical =
        SessionCollaborationProjection.read(content, "canonical", null, 100, "", "participants");
    var labels = new SessionContextLabels();
    calls.forEach(labels::register);
    var keys = canonical.items().stream().map(row -> (String) row.get("key")).toList();
    var expected = new LinkedHashMap<String, String>();
    canonical
        .items()
        .forEach(row -> expected.put((String) row.get("key"), (String) row.get("label")));
    assertThat(labels.subset(keys))
        .isEqualTo(expected)
        .containsEntry("unknown:call-1", "匿名上下文 0")
        .containsEntry("subagent:violet", "Agent 1")
        .containsEntry("main", "主 Agent")
        .containsEntry("subagent:unknown-sidechain:synthetic", "匿名上下文 3")
        .containsEntry("subagent:yarrow", "Agent 4");
    for (String selected : keys) {
      var page =
          SessionExecutionProjection.read(content, "selected", null, 1, null, "all", selected);
      assertThat(page.contextLabels())
          .containsExactlyEntriesOf(Map.of(selected, expected.get(selected)));
    }
    assertThat(
            SessionExecutionProjection.read(content, "target", null, 1, "call-5", "all")
                .contextLabels())
        .containsExactlyEntriesOf(Map.of("subagent:yarrow", expected.get("subagent:yarrow")));
    var first = SessionExecutionProjection.read(content, "pages", null, 1, null, "all");
    var second =
        SessionExecutionProjection.read(content, "pages", first.nextCursor(), 1, null, "all");
    assertThat(second.contextLabels())
        .containsExactlyEntriesOf(Map.of("subagent:violet", "Agent 1"));
    assertThat(
            SessionExecutionProjection.read(content, "failed", null, 100, null, "failed")
                .contextLabels())
        .isEmpty();
  }

  @Test
  void completeReferenceIntersectionReachesDerived269BoundWithoutArbitraryTruncation() {
    var labels = new SessionContextLabels();
    var keys = new ArrayList<String>();
    var sequence = new int[] {0};
    java.util.function.Supplier<String> next =
        () -> {
          String id = "reference-" + sequence[0]++;
          keys.add("subagent:" + id);
          labels.register(call(sequence[0], id));
          return id;
        };
    var items = new ArrayList<SessionExecutionProjection.Item>();
    for (int i = 0; i < 100; i++) {
      var group =
          new SessionExecutionProjection.Group(
              "g-" + i, i, 1, "", "subagent", next.get(), "", "", "", 1, true, "", false, false);
      items.add(new SessionExecutionProjection.Item(group, tool(next.get()), 1));
    }
    var failure = tool(next.get());
    var longest = new ArrayList<ApiResponses.ToolExecutionSummary>();
    for (int i = 0; i < 8; i++) longest.add(tool(next.get()));
    var workloads = new ArrayList<SessionExecutionProjection.Workload>();
    for (int i = 0; i < 8; i++)
      workloads.add(
          new SessionExecutionProjection.Workload(
              "subagent",
              next.get(),
              "executor_reported",
              "exec_command",
              5,
              5,
              0,
              0,
              "5",
              tool(next.get()),
              List.of(tool(next.get()), tool(next.get()), tool(next.get())),
              maximum(tool(next.get()))));
    var operations = new ArrayList<SessionExecutionProjection.LongOperation>();
    for (int i = 0; i < 3; i++)
      operations.add(new SessionExecutionProjection.LongOperation("1", tool(next.get())));
    var signals = new ArrayList<SessionExecutionProjection.WorkloadSignal>();
    for (int i = 0; i < 3; i++)
      signals.add(
          new SessionExecutionProjection.WorkloadSignal(
              "subagent",
              next.get(),
              "exec_command",
              "executor_reported",
              "1",
              1,
              1,
              0,
              0,
              new SessionExecutionProjection.LongOperation("1", tool(next.get())),
              maximum(tool(next.get()))));
    var diagnostics =
        new SessionExecutionProjection.Diagnostics(
            1,
            1,
            1,
            1,
            "failure",
            longest,
            8,
            failure,
            workloads,
            8,
            0,
            new SessionExecutionProjection.LongOperations(3, 3, 0, 0, 0, operations),
            new SessionExecutionProjection.WorkloadSignals(3, 3, 0, 0, 0, 3, signals));
    labels.register(call(900, "unreferenced"));
    var page =
        new SessionExecutionProjection.Page("1", items, 100, 0, null, null)
            .withDiagnostics(diagnostics, labels);
    assertThat(page.contextLabels().keySet())
        .containsExactlyInAnyOrderElementsOf(keys)
        .hasSize(269);
    assertThat(page.diagnostics()).isSameAs(diagnostics);
    assertThat(page.contextLabels()).doesNotContainKey("subagent:unreferenced");
  }

  @Test
  void emptyObservedInputAndIsolatedToolContextsCannotInventLabels() {
    var labels = new SessionContextLabels();
    var group =
        new SessionExecutionProjection.Group(
            "observed-input:1", 1, 1, "", "main", "", "", "", "", 0, false, "", true, false);
    var page =
        new SessionExecutionProjection.Page(
            "1",
            List.of(new SessionExecutionProjection.Item(group, tool("orphan"), 0)),
            1,
            0,
            null,
            null);
    assertThat(page.withDiagnostics(null, labels).contextLabels()).isEmpty();
    labels.register(call(1, ""));
    assertThat(page.withDiagnostics(null, labels).contextLabels())
        .containsExactlyEntriesOf(Map.of("main", "主 Agent"));
    assertThat(new SessionContextLabels().subset(List.of("main", "subagent:orphan"))).isEmpty();
  }

  private static SessionExecutionInputs.SameInputMaximum maximum(
      ApiResponses.ToolExecutionSummary tool) {
    return new SessionExecutionInputs.SameInputMaximum("1", 1, 1, 0, 0, 2, 1, 1, tool);
  }

  private static ApiResponses.ToolExecutionSummary tool(String id) {
    return SessionApiHandler.toolSummary(
        new NormalizedToolExecution(
            "tool-" + id,
            "exec_command",
            CallScope.SUBAGENT,
            "call-" + id,
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            null,
            List.of(),
            Optional.of(id),
            Optional.empty()),
        "",
        false);
  }

  private static NormalizedCall call(int index, String child) {
    return new NormalizedCall(
        "call-" + index,
        index,
        "C" + index,
        "".equals(child) ? CallScope.MAIN : CallScope.SUBAGENT,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(0, 0, 0, 0, 0),
        new NormalizedCallRequest(List.of()),
        new NormalizedCallResponse(List.of()),
        List.of(),
        List.of(),
        Map.of(),
        Map.of(),
        Optional.ofNullable(child).filter(id -> !id.isEmpty()),
        Optional.empty());
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
}
