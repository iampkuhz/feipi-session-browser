package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

/** 无 usage/turn_context 的显式用户分段不能把第二轮工具归给第一轮助手。 */
class ToolUserBoundaryTest {
  @TestFactory
  Stream<DynamicTest> explicitUserBoundaryContracts() {
    var boundaries =
        Stream.of(false, true)
            .flatMap(
                managed ->
                    Stream.of(
                        test(
                            managed, "same-timestamp-two-rounds", () -> segments(managed, 2, true)),
                        test(managed, "different-timestamps", () -> segments(managed, 2, false)),
                        test(managed, "600-rounds", () -> segments(managed, 600, true)),
                        test(
                            managed,
                            "meta-input-does-not-end-real-segment",
                            () -> metaInput(managed, false)),
                        test(
                            managed,
                            "meta-input-after-assistant-selects-next-call",
                            () -> metaInput(managed, true)),
                        test(
                            managed,
                            "assistant-before-tool-same-segment",
                            () -> sameSegment(managed)),
                        test(
                            managed,
                            "first-segment-without-assistant-fails-closed",
                            () -> firstUnfinished(managed)),
                        test(
                            managed,
                            "known-delayed-result-is-not-orphan",
                            () -> delayedResult(managed)),
                        test(
                            managed,
                            "unfinished-segment-fails-closed",
                            () -> unfinished(managed, false)),
                        test(
                            managed,
                            "unrelated-next-user-cannot-lend-owner",
                            () -> unfinished(managed, true))));
    // 复用已有独立 scope/root-spawn 行为，不重新制造另一套父子 fixture。
    var scopes =
        new ToolIdentityCollisionTest()
            .toolIdentityContractsForListAndManaged()
            .filter(
                test ->
                    test.getDisplayName().endsWith("main-and-two-children")
                        || test.getDisplayName().endsWith("root-spawn-evidence")
                        || test.getDisplayName().endsWith("inherited-spawn-is-not-root-execution"));
    return Stream.concat(boundaries, scopes);
  }

  private static void segments(boolean managed, int count, boolean sameTimestamp) throws Exception {
    var records = new ArrayList<SourceRecord>();
    for (int round = 1; round <= count; round++) {
      int timestamp = sameTimestamp ? 0 : round;
      records.add(record(records.size(), "user", round, timestamp));
      records.add(record(records.size(), "tool_use", round, timestamp));
      records.add(record(records.size(), "tool_result", round, timestamp));
      records.add(record(records.size(), "assistant", round, timestamp));
    }
    var artifact = normalize(managed, records);
    assertThat(artifact.calls()).hasSize(count);
    assertThat(artifact.toolExecutions()).hasSize(count);
    for (int round = 1; round <= count; round++) {
      var call = artifact.calls().get(round - 1);
      var tool = artifact.toolExecutions().get(round - 1);
      String expectedInput = "input-body-" + round;
      assertThat(call.callId()).isEqualTo("reply-" + round);
      assertThat(call.callIndex()).isEqualTo(round);
      assertThat(call.turnId()).isEmpty();
      assertThat(tool.toolCallId()).isEqualTo("tool-" + round);
      assertThat(tool.declaredByCallId()).as("round %s tool owner", round).isEqualTo(call.callId());
      assertThat(tool.resultConsumedByCallId()).contains(call.callId());
      assertThat(call.request().toolResultIds()).containsExactly(tool.toolCallId());
      assertThat(call.sourceUnits())
          .extracting(unit -> unit.get("text"))
          .contains("user-body-" + round, "result-body-" + round, "assistant-body-" + round);
      assertThat(call.sourceUnits())
          .anySatisfy(
              unit ->
                  assertThat(unit)
                      .containsEntry("type", "tool_use")
                      .containsEntry("id", tool.toolCallId())
                      .containsEntry("input", expectedInput));
      // 每个正文 occurrence 属于此段，而不是只检查全局尾字符串。
      assertThat(call.sourceUnits()).hasSize(4);
    }
  }

  private static void sameSegment(boolean managed) throws Exception {
    var artifact =
        normalize(
            managed,
            List.of(
                record(0, "user", 1, 0),
                record(1, "assistant", 1, 0),
                record(2, "tool_use", 1, 0),
                record(3, "tool_result", 1, 0),
                record(4, "assistant", 2, 0)));
    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.toolExecutions())
        .singleElement()
        .satisfies(
            tool -> {
              assertThat(tool.declaredByCallId()).isEqualTo("reply-1");
              assertThat(tool.resultConsumedByCallId()).contains("reply-2");
            });
  }

  private static void unfinished(boolean managed, boolean unrelatedNextUser) {
    var records =
        new ArrayList<>(
            List.of(
                record(0, "user", 1, 0),
                record(1, "assistant", 1, 0),
                record(2, "user", 2, 0),
                record(3, "tool_use", 2, 0),
                record(4, "tool_result", 2, 0)));
    if (unrelatedNextUser) {
      records.add(record(5, "user", 3, 0));
      records.add(record(6, "assistant", 3, 0));
    }
    // 必填 owner 无法诚实表达时整次拒绝投影，不借旧/远端 call、不删工具或造 call。
    assertThatThrownBy(() -> normalize(managed, records))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("TOOL_OWNER_UNAVAILABLE");
  }

  private static void firstUnfinished(boolean managed) {
    var records =
        List.of(
            record(0, "user", 1, 0), record(1, "tool_use", 1, 0), record(2, "tool_result", 1, 0));
    assertThatThrownBy(() -> normalize(managed, records))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessage("TOOL_OWNER_UNAVAILABLE");
  }

  private static void delayedResult(boolean managed) throws Exception {
    var artifact =
        normalize(
            managed,
            List.of(
                record(0, "user", 1, 0),
                record(1, "assistant", 1, 0),
                record(2, "tool_use", 1, 0),
                record(3, "user", 2, 0),
                record(4, "tool_result", 1, 0),
                record(5, "assistant", 2, 0)));
    assertThat(artifact.calls())
        .extracting(call -> call.callId())
        .containsExactly("reply-1", "reply-2");
    assertThat(artifact.toolExecutions())
        .singleElement()
        .satisfies(
            tool -> {
              assertThat(tool.toolCallId()).isEqualTo("tool-1");
              assertThat(tool.declaredByCallId()).isEqualTo("reply-1");
              assertThat(tool.resultConsumedByCallId()).contains("reply-2");
            });
    assertThat(artifact.calls().get(1).request().toolResultIds()).containsExactly("tool-1");
    assertThat(artifact.calls().get(1).sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry("tool_call_id", "tool-1")
                    .containsEntry("text", "result-body-1"));
  }

  private static void metaInput(boolean managed, boolean afterAssistant) throws Exception {
    var records = new ArrayList<SourceRecord>();
    records.add(record(0, "user", 1, 0));
    if (afterAssistant) records.add(record(records.size(), "assistant", 1, 0));
    if (afterAssistant) records.add(record(records.size(), "user", 99, 0, true));
    records.add(record(records.size(), "tool_use", 2, 0));
    if (!afterAssistant) records.add(record(records.size(), "user", 99, 0, true));
    records.add(record(records.size(), "tool_result", 2, 0));
    records.add(record(records.size(), "assistant", 2, 0));
    var artifact = normalize(managed, records);
    assertThat(artifact.calls()).hasSize(afterAssistant ? 2 : 1);
    var call = artifact.calls().getLast();
    assertThat(call.callId()).isEqualTo("reply-2");
    assertThat(call.turnId()).isEmpty();
    assertThat(artifact.toolExecutions())
        .singleElement()
        .satisfies(
            tool -> {
              assertThat(tool.declaredByCallId()).isEqualTo(call.callId());
              assertThat(tool.resultConsumedByCallId()).contains(call.callId());
            });
    assertThat(call.request().toolResultIds()).containsExactly("tool-2");
    assertThat(call.sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry("type", "user")
                    .containsEntry("text", "user-body-99")
                    .containsEntry("isMeta", true));
    assertThat(call.sourceUnits())
        .extracting(unit -> unit.get("text"))
        .contains("result-body-2", "assistant-body-2");
    assertThat(call.sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry("id", "tool-2")
                    .containsEntry("input", "input-body-2"));
    assertThat(artifact.calls().getFirst().sourceUnits())
        .anySatisfy(unit -> assertThat(unit).containsEntry("text", "user-body-1"));
  }

  private static NormalizedSessionArtifact normalize(boolean managed, List<SourceRecord> records)
      throws Exception {
    var engine = new NormalizationEngine();
    if (!managed) return engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      var artifact = content.toArtifact();
      assertThat(content.toArtifact()).isEqualTo(artifact);
      return artifact;
    }
  }

  private static SourceRecord record(int index, String type, int round, int seconds) {
    return record(index, type, round, seconds, false);
  }

  private static SourceRecord record(int index, String type, int round, int seconds, boolean meta) {
    String tool = "tool-" + round;
    String id = type.equals("assistant") ? "reply-" + round : type.equals("tool_use") ? tool : null;
    return new SourceRecord(
        "synthetic/root.jsonl#event[" + index + "]",
        index,
        type,
        Optional.ofNullable(id),
        Optional.of("synthetic-model"),
        Optional.of(
            java.time.Instant.parse("2026-01-01T00:00:00Z").plusSeconds(seconds).toString()),
        Optional.empty(),
        new SourceRecordUsage(0, 0, 0, 0),
        type.equals("tool_use")
            ? List.of(new SourceToolCall(tool, "custom", "input-body-" + round))
            : List.of(),
        type.equals("tool_result") ? Optional.of(tool) : Optional.empty(),
        type.equals("tool_use") ? Optional.of("custom") : Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        switch (type) {
          case "user" -> "user-body-" + round;
          case "assistant" -> "assistant-body-" + round;
          case "tool_result" -> "result-body-" + round;
          default -> "";
        },
        Optional.empty(),
        Optional.empty(),
        SourceTiming.empty(),
        meta,
        List.of("user", "assistant").contains(type) ? Optional.of(type) : Optional.empty());
  }

  private static DynamicTest test(boolean managed, String name, Checked action) {
    return DynamicTest.dynamicTest((managed ? "managed/" : "list/") + name, action::run);
  }

  @FunctionalInterface
  private interface Checked {
    void run() throws Exception;
  }
}
