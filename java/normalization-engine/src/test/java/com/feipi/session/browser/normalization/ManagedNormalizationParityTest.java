package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertAll;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.Random;
import org.junit.jupiter.api.Test;

/** 对照旧列表路径的完整对象，保留文本 occurrence、关系和 header 的精确语义。 */
class ManagedNormalizationParityTest {
  @Test
  void firstUserInputBelongsToTheFollowingCallRatherThanThePreparationCall() throws Exception {
    for (boolean preparation : List.of(false, true)) {
      var records = new ArrayList<SourceRecord>();
      if (preparation) {
        records.add(record(0, "main", "response_item", "preparation response", "preparation-text"));
        records.add(record(1, "main", "assistant", "", "token_count:preparation"));
      }
      records.add(record(records.size(), "main", "user", "synthetic first question", "question"));
      records.add(record(records.size(), "main", "assistant", "synthetic answer", "answer"));
      try (var sequence = SourceRecordSequence.fromList(records)) {
        var engine = new NormalizationEngine();
        for (var content :
            List.of(
                engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()),
                engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of()))) {
          var calls = content.toArtifact().calls();
          assertThat(calls).hasSize(preparation ? 2 : 1);
          assertThat(calls.getLast().sourceUnits())
              .filteredOn(unit -> "user".equals(unit.get("role")))
              .extracting(unit -> unit.get("text"))
              .containsExactly("synthetic first question");
          if (preparation) {
            assertThat(calls.getFirst().sourceUnits())
                .noneMatch(unit -> "user".equals(unit.get("role")));
          }
        }
      }
    }
  }

  @Test
  void resultOccurrenceSummaryDistinguishesSharedConsumerFromTailResult() throws Exception {
    for (boolean tail : List.of(false, true)) {
      var records =
          tail
              ? List.of(
                  resultOccurrenceRecord(0, "assistant", ""),
                  resultOccurrenceRecord(1, "tool_result", "R1"),
                  resultOccurrenceRecord(2, "assistant", ""),
                  resultOccurrenceRecord(3, "tool_result", "R2"))
              : List.of(
                  resultOccurrenceRecord(0, "assistant", ""),
                  resultOccurrenceRecord(1, "tool_result", "R1"),
                  resultOccurrenceRecord(3, "tool_result", "R2"),
                  resultOccurrenceRecord(4, "assistant", ""));
      var engine = new NormalizationEngine();
      try (var sequence = SourceRecordSequence.fromList(records)) {
        for (var content :
            List.of(
                engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()),
                engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of()))) {
          var artifact = content.toArtifact();
          assertThat(artifact.calls()).hasSize(2);
          assertThat(artifact.toolExecutions()).hasSize(1);
          var owner = artifact.calls().getFirst();
          var following = artifact.calls().getLast();
          var tool = artifact.toolExecutions().getFirst();
          assertThat(tool.declaredByCallId()).isEqualTo(owner.callId());
          assertThat(owner.request().toolResultIds()).isEmpty();
          assertThat(owner.sourceUnits())
              .anySatisfy(unit -> assertThat(unit).containsEntry("input", "input T"));
          assertThat(artifact.sourceUnitCatalog().values())
              .filteredOn(entry -> "tool_result".equals(entry.unitType()))
              .hasSize(2)
              .extracting(entry -> entry.text().orElseThrow())
              .containsExactlyInAnyOrder("R1", "R2");
          var texts = following.sourceUnits().stream().map(unit -> unit.get("text")).toList();
          if (tail) {
            assertThat(tool.resultConsumedByCallId()).isEmpty();
            assertThat(following.request().toolResultIds()).containsExactly(tool.toolCallId());
            assertThat(texts).contains("R1").doesNotContain("R2");
          } else {
            assertThat(tool.resultConsumedByCallId()).contains(following.callId());
            assertThat(following.request().toolResultIds())
                .containsExactly(tool.toolCallId(), tool.toolCallId());
            assertThat(texts).containsSubsequence("R1", "R2");
          }
        }
      }
    }
  }

  @Test
  void resultOccurrencesKeepTheirOwnFollowingRequests() throws Exception {
    var records =
        List.of(
            resultOccurrenceRecord(0, "assistant", ""),
            resultOccurrenceRecord(1, "tool_result", "R1"),
            resultOccurrenceRecord(2, "assistant", ""),
            resultOccurrenceRecord(3, "tool_result", "R2"),
            resultOccurrenceRecord(4, "assistant", ""));
    var engine = new NormalizationEngine();
    try (var sequence = SourceRecordSequence.fromList(records)) {
      assertAll(
          "each result occurrence keeps its own request",
          () ->
              assertResultOccurrenceRequests(
                  engine
                      .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of())
                      .toArtifact(),
                  "ordinary"),
          () ->
              assertResultOccurrenceRequests(
                  engine
                      .normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
                      .toArtifact(),
                  "managed"));
    }
  }

  @Test
  void identicalAndEmptyResultsKeepDistinctSourceAnchors() throws Exception {
    for (String body : List.of("same result", "")) {
      var records =
          List.of(
              resultOccurrenceRecord(0, "assistant", ""),
              resultOccurrenceRecord(1, "tool_result", body),
              resultOccurrenceRecord(2, "assistant", ""),
              resultOccurrenceRecord(1, "tool_result", body),
              resultOccurrenceRecord(4, "assistant", ""),
              resultOccurrenceRecord(5, "tool_result", body));
      var engine = new NormalizationEngine();
      var ordinary =
          engine
              .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of())
              .toArtifact();
      try (var sequence = SourceRecordSequence.fromList(records)) {
        var managed =
            engine
                .normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
                .toArtifact();
        for (var artifact : List.of(ordinary, managed)) {
          assertThat(artifact.sourceUnitCatalog().values())
              .filteredOn(entry -> "tool_result".equals(entry.unitType()))
              .hasSize(3)
              .allSatisfy(entry -> assertThat(entry.text()).contains(body));
          assertThat(artifact.calls().getFirst().sourceUnits())
              .noneMatch(unit -> unit.containsKey("result_source_unit_key"));
          for (int callIndex = 1; callIndex < 3; callIndex++) {
            String key = "tool-result:" + (2 * callIndex - 1) + ":" + records.get(1).locator();
            assertThat(artifact.calls().get(callIndex).sourceUnits())
                .filteredOn(unit -> "tool_result".equals(unit.get("type")))
                .singleElement()
                .satisfies(unit -> assertThat(unit).containsEntry("result_source_unit_key", key));
            assertThat(artifact.sourceUnitCatalog()).containsKey(key);
          }
          assertThat(artifact.toolExecutions().getFirst().resultConsumedByCallId()).isEmpty();
        }
        assertThat(managed.calls()).isEqualTo(ordinary.calls());
      }
    }
  }

  private static SourceRecord resultOccurrenceRecord(int index, String type, String body) {
    boolean assistant = "assistant".equals(type);
    return new SourceRecord(
        "synthetic/occurrences#event[" + index + "]",
        index,
        type,
        assistant ? Optional.of("F" + (index / 2 + 1)) : Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        assistant ? new SourceRecordUsage(1, 0, 0, 1) : SourceRecordUsage.empty(),
        index == 0 ? List.of(new SourceToolCall("T", "exec_command", "input T")) : List.of(),
        assistant ? Optional.empty() : Optional.of("T"),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        body);
  }

  private static void assertResultOccurrenceRequests(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact, String path) {
    assertThat(artifact.calls()).as(path).hasSize(3);
    assertThat(artifact.toolExecutions()).as(path).hasSize(1);
    var owner = artifact.calls().getFirst();
    var second = artifact.calls().get(1);
    var third = artifact.calls().getLast();
    var tool = artifact.toolExecutions().getFirst();
    assertThat(tool.declaredByCallId()).as(path).isEqualTo(owner.callId());
    assertThat(owner.response().toolCallIds()).containsExactly(tool.toolCallId());
    assertThat(artifact.calls())
        .allSatisfy(
            call -> {
              assertThat(call.usage().fresh()).isEqualTo(1);
              assertThat(call.usage().output()).isEqualTo(1);
            });
    assertThat(owner.sourceUnits())
        .anySatisfy(unit -> assertThat(unit).containsEntry("input", "input T"));
    assertThat(artifact.sourceUnitCatalog().values())
        .filteredOn(entry -> "tool_result".equals(entry.unitType()))
        .hasSize(2)
        .extracting(entry -> entry.text().orElseThrow())
        .containsExactlyInAnyOrder("R1", "R2");
    for (var call : List.of(second, third)) {
      String text = call == second ? "R1" : "R2";
      var entry =
          artifact.sourceUnitCatalog().values().stream()
              .filter(value -> value.text().filter(text::equals).isPresent())
              .findFirst()
              .orElseThrow();
      assertThat(call.sourceUnits())
          .filteredOn(unit -> "tool_result".equals(unit.get("type")))
          .singleElement()
          .satisfies(
              unit -> assertThat(unit).containsEntry("result_source_unit_key", entry.unitKey()));
    }
    assertAll(
        path,
        () -> assertThat(owner.request().toolResultIds()).isEmpty(),
        () ->
            assertThat(owner.sourceUnits())
                .noneMatch(unit -> "tool_result".equals(unit.get("type"))),
        () -> assertThat(second.request().toolResultIds()).containsExactly(tool.toolCallId()),
        () -> assertThat(third.request().toolResultIds()).containsExactly(tool.toolCallId()),
        () ->
            assertThat(second.sourceUnits().stream().map(unit -> unit.get("text")).toList())
                .contains("R1")
                .doesNotContain("R2"),
        () ->
            assertThat(third.sourceUnits().stream().map(unit -> unit.get("text")).toList())
                .contains("R2")
                .doesNotContain("R1"),
        () -> assertThat(tool.resultConsumedByCallId()).isEmpty());
  }

  @Test
  void deferredResultDoesNotMoveLateResponseToFollowingCall() throws Exception {
    var records =
        List.of(
            orphanRecord(1, false, "tool_use", "T", "input T"),
            orphanRecord(2, false, "tool_result", "T", "R"),
            orphanRecord(3, false, "assistant", "token_usage_record:F1", ""),
            lateResponseRecord(4, "response_item", "A1"),
            lateResponseRecord(5, "user", "U2"),
            orphanRecord(6, false, "assistant", "token_usage_record:F2", ""));
    var engine = new NormalizationEngine();
    try (var sequence = SourceRecordSequence.fromList(records)) {
      assertAll(
          "late response stays with declaring call",
          () ->
              assertDeferredResponse(
                  engine
                      .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of())
                      .toArtifact(),
                  "ordinary"),
          () ->
              assertDeferredResponse(
                  engine
                      .normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
                      .toArtifact(),
                  "managed"));
    }
  }

  private static SourceRecord lateResponseRecord(int index, String type, String text) {
    return new SourceRecord(
        "synthetic/parent#event[" + index + "]",
        index,
        type,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        text);
  }

  private static void assertDeferredResponse(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact, String path) {
    assertThat(artifact.calls()).as(path).hasSize(2);
    assertThat(artifact.toolExecutions()).as(path).hasSize(1);
    var first = artifact.calls().getFirst();
    var next = artifact.calls().getLast();
    var tool = artifact.toolExecutions().getFirst();
    assertThat(first.usage().fresh()).isEqualTo(1);
    assertThat(next.usage().fresh()).isEqualTo(1);
    assertThat(tool.declaredByCallId()).isEqualTo(first.callId());
    assertThat(tool.resultConsumedByCallId()).contains(next.callId());
    assertThat(first.request().toolResultIds()).isEmpty();
    assertThat(next.request().toolResultIds()).containsExactly(tool.toolCallId());
    assertThat(first.sourceUnits())
        .anySatisfy(unit -> assertThat(unit).containsEntry("input", "input T"));
    assertThat(artifact.sourceUnitCatalog().values())
        .anySatisfy(
            entry -> {
              assertThat(entry.unitType()).isEqualTo("tool_result");
              assertThat(entry.text()).contains("R");
            });
    assertAll(
        path,
        () ->
            assertThat(first.sourceUnits().stream().map(unit -> unit.get("text")).toList())
                .contains("A1")
                .doesNotContain("R", "U2"),
        () ->
            assertThat(next.sourceUnits().stream().map(unit -> unit.get("text")).toList())
                .containsSubsequence("R", "U2")
                .doesNotContain("A1"));
  }

  @Test
  void closingFrameResultMovesOnlyToActualFollowingFrameInSameScope() throws Exception {
    var records =
        List.of(
            orphanRecord(1, false, "tool_use", "self-tool", "synthetic input"),
            orphanRecord(2, false, "tool_result", "self-tool", "synthetic own result"),
            orphanRecord(3, false, "assistant", "token_usage_record:self-response", ""),
            orphanRecord(4, true, "assistant", "token_usage_record:child-response", ""),
            orphanRecord(5, false, "assistant", "token_usage_record:following-response", ""));
    var engine = new NormalizationEngine();
    try (var sequence = SourceRecordSequence.fromList(records)) {
      for (var content :
          List.of(
              engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()),
              engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of()))) {
        var artifact = content.toArtifact();
        assertThat(artifact.calls()).hasSize(3);
        var owner = artifact.calls().getFirst();
        var child = artifact.calls().get(1);
        var following = artifact.calls().getLast();
        var tool = artifact.toolExecutions().getFirst();
        assertThat(tool.declaredByCallId()).isEqualTo(owner.callId());
        assertThat(tool.resultConsumedByCallId()).contains(following.callId());
        assertThat(owner.request().toolResultIds()).isEmpty();
        assertThat(child.request().toolResultIds()).isEmpty();
        assertThat(owner.sourceUnits()).noneMatch(unit -> "tool_result".equals(unit.get("type")));
        assertThat(child.sourceUnits()).noneMatch(unit -> "tool_result".equals(unit.get("type")));
        assertThat(following.request().toolResultIds()).containsExactly(tool.toolCallId());
        assertThat(following.sourceUnits())
            .anySatisfy(unit -> assertThat(unit).containsEntry("text", "synthetic own result"));
      }
    }
  }

  @Test
  void closingFrameDoesNotConsumeOwnToolResult() throws Exception {
    var records =
        List.of(
            orphanRecord(1, false, "tool_use", "self-tool", "synthetic input"),
            orphanRecord(2, false, "tool_result", "self-tool", "synthetic own result"),
            new SourceRecord(
                "synthetic/parent#event[3]",
                3,
                "assistant",
                Optional.of("token_usage_record:self-response"),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                new SourceRecordUsage(1, 0, 0, 1),
                List.of(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty()));
    var engine = new NormalizationEngine();
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var ordinary = engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
      var managed = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertAll(
          "closing frame causal boundary",
          () -> assertClosingFrameResult(ordinary.toArtifact(), "ordinary"),
          () -> assertClosingFrameResult(managed.toArtifact(), "managed"));
    }
  }

  private static void assertClosingFrameResult(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact, String path) {
    assertThat(artifact.calls()).as(path).hasSize(1);
    assertThat(artifact.toolExecutions()).as(path).hasSize(1);
    var call = artifact.calls().getFirst();
    var tool = artifact.toolExecutions().getFirst();
    assertThat(call.usage().fresh()).as(path).isEqualTo(1);
    assertThat(call.usage().output()).as(path).isEqualTo(1);
    assertThat(call.response().toolCallIds()).as(path).containsExactly(tool.toolCallId());
    assertThat(tool.declaredByCallId()).as(path).isEqualTo(call.callId());
    assertThat(call.sourceUnits())
        .as(path + " input retained")
        .anySatisfy(unit -> assertThat(unit).containsEntry("input", "synthetic input"));
    assertThat(artifact.sourceUnitCatalog().values())
        .as(path + " result retained")
        .anySatisfy(
            entry -> {
              assertThat(entry.unitType()).isEqualTo("tool_result");
              assertThat(entry.text()).contains("synthetic own result");
            });
    assertAll(
        path,
        () -> assertThat(tool.resultConsumedByCallId()).isEmpty(),
        () -> assertThat(call.request().toolResultIds()).isEmpty(),
        () ->
            assertThat(call.sourceUnits())
                .noneMatch(unit -> "tool_result".equals(unit.get("type"))));
  }

  @Test
  void orphanToolInputWithoutModelOwnerSurvivesOrdinaryAndManagedContent() throws Exception {
    // 同 raw parent/child checkpoint 的 SourceRecord 投影；真实 adapter 链由 scan-engine 覆盖。
    var childRelation =
        new SourceRecordRelation(
            Optional.of("synthetic-orphan-child-v52"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    var records =
        List.of(
            orphanRecord(
                1,
                false,
                "tool_use",
                "orphan-parent-spawn-v54",
                "{\"message\":\"Synthetic interrupted child task: inspect recorded command failure;"
                    + " do not execute a real script.\"}"),
            orphanRecord(
                2,
                false,
                "tool_result",
                "orphan-parent-spawn-v54",
                "{\"agent_id\":\"synthetic-orphan-child-v52\"}"),
            orphanRecord(
                3, false, "assistant", "token_usage_record:orphan-parent-response-v54", ""),
            orphanRecord(
                1,
                true,
                "tool_use",
                "orphan-command-v52",
                "{\"cmd\":\"node synthetic-orphan-check.js --case no-owner\"}"),
            orphanRecord(
                2,
                true,
                "tool_result",
                "orphan-command-v52",
                "Synthetic recorded error, command not executed"),
            SourceRecord.of("synthetic/child#event[3]", 3, "tool_observation")
                .withRelation(childRelation)
                .withToolObservation(
                    Optional.of(
                        new com.feipi.session.browser.domain.source.SourceToolObservation(
                            "orphan-command-v52",
                            500_000_000L,
                            7,
                            "completed",
                            null,
                            "executor_reported",
                            "codex:exec_command_end#event[3]",
                            null))));
    var engine = new NormalizationEngine();
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var ordinary = engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
      var managed = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertAll(
          "ordinary and managed retain owner-independent input",
          () -> assertOrphanInput(ordinary.toArtifact(), "ordinary"),
          () -> assertOrphanInput(managed.toArtifact(), "managed"));
    }
  }

  private static void assertOrphanInput(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact, String path) {
    assertThat(artifact.calls()).as(path + " parent call").hasSize(1);
    assertThat(artifact.toolExecutions()).as(path + " executions").hasSize(2);
    var child =
        artifact.toolExecutions().stream()
            .filter(tool -> tool.name().equals("exec_command"))
            .findFirst()
            .orElseThrow();
    assertThat(child.declaredByCallId()).isEqualTo("unknown");
    assertThat(child.scope().getValue()).isEqualTo("subagent");
    assertThat(child.subagentId()).contains("synthetic-orphan-child-v52");
    assertThat(child.durationMs()).isEqualTo(500L);
    assertThat(child.exitCode()).contains(7);
    assertThat(child.resultConsumedByCallId()).isEmpty();
    assertThat(artifact.sourceUnitCatalog().values())
        .anySatisfy(
            entry -> {
              assertThat(entry.unitType()).isEqualTo("tool_result");
              assertThat(entry.label()).contains(child.toolCallId());
              assertThat(entry.text()).contains("Synthetic recorded error, command not executed");
            });
    assertThat(artifact.sourceUnitCatalog().values())
        .as(path + " orphan tool input must retain the original command")
        .anySatisfy(
            entry -> {
              assertThat(entry.direction().getValue()).isEqualTo("response");
              assertThat(entry.payload()).isInstanceOf(java.util.Map.class);
              var payload = (java.util.Map<?, ?>) entry.payload();
              assertThat(payload.get("type")).isEqualTo("tool_use");
              assertThat(payload.get("id")).isEqualTo(child.toolCallId());
              assertThat(payload.get("name")).isEqualTo(child.name());
              assertThat(payload.get("input"))
                  .isEqualTo("{\"cmd\":\"node synthetic-orphan-check.js --case no-owner\"}");
            });
  }

  private static SourceRecord orphanRecord(
      int index, boolean child, String type, String id, String body) {
    String name = child ? "exec_command" : "spawn_agent";
    return new SourceRecord(
        "synthetic/" + (child ? "child" : "parent") + "#event[" + index + "]",
        index,
        type,
        Optional.of(id),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "assistant".equals(type) ? new SourceRecordUsage(1, 1, 0, 0) : SourceRecordUsage.empty(),
        "tool_use".equals(type) ? List.of(new SourceToolCall(id, name, body)) : List.of(),
        "tool_result".equals(type) ? Optional.of(id) : Optional.empty(),
        "tool_use".equals(type) ? Optional.of(name) : Optional.empty(),
        Optional.empty(),
        child
            ? new SourceRecordRelation(
                Optional.of("synthetic-orphan-child-v52"),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty())
            : SourceRecordRelation.empty(),
        "tool_result".equals(type) ? body : "",
        Optional.empty(),
        Optional.empty());
  }

  @Test
  void recordedTailResultsRemainIndependentOfMissingConsumersIncludingEmptyBodies()
      throws Exception {
    for (String body : List.of("synthetic tail result", "")) {
      for (boolean managed : List.of(false, true)) {
        var records =
            List.of(
                record(0, "main", "assistant", "declaring response", "declare"),
                record(1, "main", "tool_result", body, "result"));
        try (var sequence = SourceRecordSequence.fromList(records)) {
          var engine = new NormalizationEngine();
          var content =
              managed
                  ? engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
                  : engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
          var artifact = content.toArtifact();
          assertThat(artifact.calls()).hasSize(1);
          assertThat(artifact.toolExecutions()).hasSize(1);
          var tool = artifact.toolExecutions().getFirst();
          assertThat(tool.resultConsumedByCallId()).isEmpty();
          assertThat(artifact.calls().getFirst().request().toolResultIds()).isEmpty();
          assertThat(artifact.calls().getFirst().sourceUnits())
              .noneMatch(unit -> "tool_result".equals(unit.get("type")));
          assertThat(artifact.session().get("consumedResults")).isEqualTo(0);
          assertThat(content.header().totals().get("sourceUnitCatalog")).isEqualTo(1L);
          assertThat(artifact.sourceUnitCatalog().values())
              .singleElement()
              .satisfies(
                  entry -> {
                    assertThat(entry.unitType()).isEqualTo("tool_result");
                    assertThat(entry.label()).contains(tool.toolCallId());
                    assertThat(entry.text()).contains(body);
                  });
          assertThat(content.toArtifact()).isEqualTo(artifact);
        }
      }
    }
  }

  @Test
  void onlyAnActualFollowingFrameConsumesTheRecordedResult() throws Exception {
    var records =
        List.of(
            record(0, "main", "assistant", "declaring response", "declare"),
            record(1, "main", "tool_result", "synthetic result", "result"),
            SourceRecord.of("synthetic/main#event[2]", 2, "assistant"));
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var engine = new NormalizationEngine();
      for (var content :
          List.of(
              engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()),
              engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of()))) {
        var artifact = content.toArtifact();
        var tool = artifact.toolExecutions().getFirst();
        assertThat(tool.resultConsumedByCallId()).contains(artifact.calls().getLast().callId());
        assertThat(artifact.calls().getFirst().request().toolResultIds()).isEmpty();
        assertThat(artifact.calls().getLast().request().toolResultIds())
            .containsExactly(tool.toolCallId());
        assertThat(artifact.sourceUnitCatalog().values())
            .singleElement()
            .satisfies(entry -> assertThat(entry.text()).contains("synthetic result"));
      }
    }
  }

  @Test
  void globalRelationsBodiesErrorsUnknownTimingAndRepeatedIdsMatchLegacyTwice() throws Exception {
    var records = new ArrayList<SourceRecord>();
    records.add(record(0, "main", "user", "question", "u"));
    records.add(record(1, "child", "assistant", "child answer", "child-call"));
    records.add(record(2, "main", "tool_use", "", "shared-tool"));
    records.add(record(3, "main", "assistant", "same body", "token_count:close"));
    records.add(record(4, "main", "response_item", "late response", "late"));
    records.add(record(5, "main", "tool_result", "result one", "result"));
    records.add(record(6, "main", "tool_result", "result two", "result"));
    records.add(record(7, "main", "assistant", "same body", "same-call-7"));
    records.add(record(8, "main", "assistant", "", "same-call-8"));
    records.add(record(9, "main", "tool_use", "", "shared-tool"));
    records.add(record(10, "main", "response_item", "EOF response", "late"));
    records.add(record(11, "main", "unknown-type", "not retained", "unknown"));
    records.add(record(12, "main", "unknown-type", "not retained twice", "unknown"));
    records.add(record(13, "main", "task", "", "task"));
    records.add(record(14, "main", "task", "", "task"));
    compare(records);
  }

  @Test
  void deterministicInterleavingMatchesLegacyWithoutBodyDeduplication() throws Exception {
    for (int seed = 0; seed < 24; seed++) {
      Random random = new Random(seed);
      var records = new ArrayList<SourceRecord>();
      String[] types = {"assistant", "user", "response_item", "tool_use", "tool_result", "neutral"};
      for (int index = 0; index < 45; index++) {
        String type = types[random.nextInt(types.length)];
        String scope = random.nextBoolean() ? "main" : "child";
        // 保留全部随机记录，但先显式闭合旧段；未完成工具段另有严格失败回归。
        if ("user".equals(type)) {
          records.add(
              record(records.size(), scope, "assistant", "segment completion", "close-" + index));
        }
        records.add(
            record(
                records.size(),
                scope,
                type,
                index % 3 == 0 ? "" : "repeated text",
                index % 5 == 0 ? "token_count:closing-" + index : "call-" + index));
      }
      for (String scope : List.of("main", "child")) {
        records.add(
            record(records.size(), scope, "assistant", "segment completion", "end-" + scope));
      }
      compare(records);
    }
  }

  @Test
  void duplicateCallIdsPreserveContentButBothArtifactPathsRejectThem() throws Exception {
    var records =
        List.of(
            record(0, "main", "assistant", "first occurrence", "duplicate"),
            record(1, "main", "tool_result", "result occurrence", "result"),
            record(2, "main", "assistant", "second occurrence", "duplicate"));
    var engine = new NormalizationEngine();
    var legacy = engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var managed = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertThat(managed.header()).isEqualTo(legacy.header());
      for (int pass = 0; pass < 2; pass++) {
        var expectedCalls =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedCall>();
        var actualCalls =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedCall>();
        var expectedTools =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedToolExecution>();
        var actualTools =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedToolExecution>();
        try (var cursor = legacy.openCursor()) {
          while (cursor.hasNext()) {
            var unit = cursor.next();
            expectedCalls.addAll(unit.calls());
            expectedTools.addAll(unit.toolExecutions());
          }
        }
        try (var cursor = managed.openCursor()) {
          while (cursor.hasNext()) {
            var unit = cursor.next();
            actualCalls.addAll(unit.calls());
            actualTools.addAll(unit.toolExecutions());
          }
        }
        assertThat(actualCalls).isEqualTo(expectedCalls);
        assertThat(actualTools).isEqualTo(expectedTools);
      }
      assertThatThrownBy(legacy::toArtifact).isInstanceOf(IllegalArgumentException.class);
      assertThatThrownBy(managed::toArtifact).isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void locatedReadsAreLinearAndFailuresAreNotEmptySuccess() throws Exception {
    var records = new ArrayList<SourceRecord>();
    for (int i = 0; i < 80; i++)
      records.add(record(i, "main", "assistant", "body-" + i, "call-" + i));
    var engine = new NormalizationEngine();
    var sequence = new TrackingSequence(records);
    try {
      var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertThat(sequence.reads).isEqualTo(records.size());
      assertThat(content.toArtifact())
          .isEqualTo(engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of()));
      assertThat(sequence.reads).isEqualTo(records.size() * 2);
      assertThat(sequence.starts.stream().filter(value -> value > 0).count()).isEqualTo(79);
      sequence.broken = true;
      assertThatThrownBy(content::toArtifact)
          .isInstanceOf(IOException.class)
          .hasMessageContaining("corrupt");
      sequence.broken = false;
      var cursor = content.openCursor();
      try {
        cursor.close();
        assertThatThrownBy(cursor::hasNext).isInstanceOf(IOException.class);
      } finally {
        cursor.close();
      }
      sequence.close();
      assertThatThrownBy(content::toArtifact)
          .isInstanceOf(IOException.class)
          .hasMessageContaining("closed");
    } finally {
      sequence.close();
    }
  }

  @Test
  void unsupportedManagedProviderIsExplicitlyRejected() throws Exception {
    try (var sequence = SourceRecordSequence.fromList(List.of())) {
      assertThatThrownBy(
              () ->
                  new NormalizationEngine()
                      .normalizeContent(NormalizedAgent.QODER, sequence, List.of(), List.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("CODEX");
    }
  }

  private static void compare(List<SourceRecord> records) throws Exception {
    var engine = new NormalizationEngine();
    var expected = engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    try (var sequence = new TrackingSequence(records)) {
      var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      var expectedHeader =
          engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()).header();
      assertThat(content.header()).isEqualTo(expectedHeader);
      for (int pass = 0; pass < 2; pass++) assertThat(content.toArtifact()).isEqualTo(expected);
      assertThat(sequence.closed).isFalse();
    }
  }

  private static SourceRecord record(
      int index, String scope, String type, String text, String callId) {
    var relation =
        "child".equals(scope)
            ? new SourceRecordRelation(
                Optional.of("child"),
                Optional.empty(),
                Optional.of("shared-tool"),
                Optional.empty(),
                Optional.of("spawn_agent"))
            : SourceRecordRelation.empty();
    SourceTiming timing =
        "task".equals(type)
            ? new SourceTiming(
                index % 2 == 1 ? "task_started" : "task_complete",
                "task-turn",
                Optional.of("2026-01-01T00:00:00Z"),
                Optional.of("2026-01-01T00:00:02Z"),
                OptionalLong.of(2000),
                OptionalLong.of(1000),
                OptionalLong.of(500),
                "event-" + index)
            : SourceTiming.empty();
    return new SourceRecord(
        "synthetic/" + scope + "#event[" + index + "]",
        index,
        type,
        Optional.of(callId),
        Optional.of("synthetic-model"),
        Optional.of("2026-01-01T00:00:01Z"),
        Optional.of("turn-" + index % 2),
        new SourceRecordUsage(index % 4, 2, 1, index % 3),
        List.of("assistant", "tool_use").contains(type)
            ? List.of(
                new SourceToolCall("shared-tool", "synthetic-tool", "{\"index\":" + index + "}"))
            : List.of(),
        "tool_result".equals(type) ? Optional.of("shared-tool") : Optional.empty(),
        "tool_use".equals(type) ? Optional.of("synthetic-tool") : Optional.empty(),
        "tool_result".equals(type) || "tool_use".equals(type)
            ? Optional.of("error-" + index)
            : Optional.empty(),
        relation,
        text,
        Optional.empty(),
        Optional.empty(),
        timing,
        false,
        List.of("assistant", "user").contains(type) ? Optional.of(type) : Optional.empty());
  }

  private static final class TrackingSequence implements SourceRecordSequence {
    private final List<SourceRecord> records;
    private final List<Long> starts = new ArrayList<>();
    private int reads;
    private boolean closed;
    private boolean broken;

    private TrackingSequence(List<SourceRecord> records) {
      this.records = List.copyOf(records);
    }

    @Override
    public long recordCount() {
      return records.size();
    }

    @Override
    public RecordCursor openCursor(long ordinal) throws IOException {
      if (closed) throw new IOException("closed sequence");
      if (ordinal < 0 || ordinal > records.size()) throw new IllegalArgumentException("ordinal");
      starts.add(ordinal);
      return new RecordCursor() {
        private int position = (int) ordinal;
        private boolean cursorClosed;

        @Override
        public boolean hasNext() throws IOException {
          if (closed || cursorClosed) throw new IOException("closed cursor");
          if (broken) throw new IOException("corrupt sequence");
          return position < records.size();
        }

        @Override
        public SourceRecord next() throws IOException {
          if (!hasNext()) throw new NoSuchElementException();
          reads++;
          return records.get(position++);
        }

        @Override
        public void close() {
          cursorClosed = true;
        }
      };
    }

    @Override
    public void close() {
      closed = true;
    }
  }
}
