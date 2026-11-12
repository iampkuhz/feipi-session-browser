package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceToolCall;
import com.feipi.session.browser.domain.source.SourceToolObservation;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 观测只补充稳定声明，物理顺序和同名进程不能改变归属或计数。 */
class ToolObservationTest {
  @Test
  void scopedIdsAndReorderedEndsAgreeForListAndManaged() throws Exception {
    for (boolean early : List.of(false, true)) {
      var records = new ArrayList<SourceRecord>();
      var ends =
          List.of(
              end("main", "same", 2_000_000_001L),
              end("child", "same", 0L),
              end("foreign", "same", 9_000_000_000L),
              end("main", "orphan", 7L));
      if (early) records.addAll(ends);
      records.add(declaration("main", "a", "same"));
      records.add(declaration("child", "b", "same"));
      records.add(declaration("main", "c", "other"));
      if (!early) records.addAll(ends);
      records.addAll(ends);
      var artifact = compare(records);
      assertThat(artifact.calls()).hasSize(3);
      assertThat(artifact.toolExecutions()).hasSize(3);
      var main = artifact.toolExecutions().get(0);
      var child = artifact.toolExecutions().get(1);
      assertThat(main.toolCallId()).isNotEqualTo(child.toolCallId());
      assertThat(main.durationMs()).isEqualTo(2000L);
      assertThat(main.observation().orElseThrow().durationNanos()).isEqualTo(2_000_000_001L);
      assertThat(child.durationMs()).isZero();
      assertThat(artifact.toolExecutions().get(2).durationMs()).isNull();
      assertThat(main.resultConsumedByCallId()).isEmpty();
      assertThat(main.status()).isEmpty();
      assertThat(main.observation().orElseThrow().status()).isEqualTo("completed");
    }
  }

  @Test
  void conflictsAndAmbiguousRepeatedDeclarationsNeverChooseLast() throws Exception {
    for (boolean reversed : List.of(false, true)) {
      var a = end("main", "tool", 0L);
      var b = end("main", "tool", 1L);
      var artifact =
          compare(List.of(declaration("main", "a", "tool"), reversed ? b : a, reversed ? a : b, a));
      var tool = artifact.toolExecutions().getFirst();
      assertThat(tool.durationMs()).isNull();
      assertThat(tool.exitCode()).isEmpty();
      assertThat(tool.observation().orElseThrow().issue()).isEqualTo("conflicting_observations");
    }
    var ambiguous =
        compare(
            List.of(
                declaration("main", "a", "tool"),
                end("main", "tool", 0L),
                declaration("main", "b", "tool")));
    assertThat(ambiguous.toolExecutions())
        .allSatisfy(
            tool -> {
              assertThat(tool.durationMs()).isNull();
              assertThat(tool.observation()).isEmpty();
            });
  }

  @Test
  void sameOriginDifferentExecutionScopesAndConflictingExitOrStatusAreNotMerged() throws Exception {
    var records =
        List.of(
            inScope(declaration("shared", "a", "tool"), "one"),
            inScope(declaration("shared", "b", "tool"), "two"),
            inScope(end("shared", "tool", 0L), "one"),
            inScope(end("shared", "tool", 9L), "two"));
    var artifact = compare(records);
    assertThat(artifact.toolExecutions()).hasSize(2);
    assertThat(artifact.toolExecutions().get(0).observation().orElseThrow().durationNanos())
        .isZero();
    assertThat(artifact.toolExecutions().get(1).observation().orElseThrow().durationNanos())
        .isEqualTo(9L);
    for (var value :
        List.of(
            new SourceToolObservation(
                "tool", 0L, 1, "completed", "same-process", "executor_reported", "safe", null),
            new SourceToolObservation(
                "tool", 0L, 0, "failed", "same-process", "executor_reported", "safe", null),
            new SourceToolObservation(
                "tool",
                0L,
                0,
                "completed",
                "different-process",
                "executor_reported",
                "safe",
                null))) {
      var conflicted =
          compare(
              List.of(
                  declaration("main", "a", "tool"),
                  end("main", "tool", 0L),
                  end("main", "tool", 0L).withToolObservation(Optional.of(value))));
      assertThat(conflicted.toolExecutions().getFirst().observation().orElseThrow().issue())
          .isEqualTo("conflicting_observations");
    }
  }

  private static SourceRecord inScope(SourceRecord value, String scope) {
    return new SourceRecord(
        value.locator(),
        value.eventIndex(),
        value.eventType(),
        value.callId(),
        value.model(),
        value.timestamp(),
        value.turnId(),
        value.usage(),
        value.toolCalls(),
        value.toolUseId(),
        value.toolName(),
        value.toolError(),
        new SourceRecordRelation(
            Optional.of(scope),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty()),
        value.content(),
        value.responseMessageId(),
        value.responseStopReason(),
        value.timing(),
        value.metaContext(),
        value.messageRole(),
        value.toolObservation());
  }

  private static NormalizedSessionArtifact compare(List<SourceRecord> records) throws Exception {
    var engine = new NormalizationEngine();
    var expected = engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var managed = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertThat(managed.toArtifact()).isEqualTo(expected);
    }
    return expected;
  }

  private static SourceRecord declaration(String origin, String call, String tool) {
    return new SourceRecord(
        origin + "#event[1]",
        1,
        "assistant",
        Optional.of(call),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(new SourceToolCall(tool, "exec_command", "{}")),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        "");
  }

  private static SourceRecord end(String origin, String tool, Long duration) {
    return SourceRecord.of(origin + "#event[2]", 2, "event_msg")
        .withToolObservation(
            Optional.of(
                new SourceToolObservation(
                    tool,
                    duration,
                    0,
                    "completed",
                    "same-process",
                    "executor_reported",
                    "codex:exec_command_end#event[2]",
                    null)));
  }
}
