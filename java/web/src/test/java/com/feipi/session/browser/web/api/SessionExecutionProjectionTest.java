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
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                2L,
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
