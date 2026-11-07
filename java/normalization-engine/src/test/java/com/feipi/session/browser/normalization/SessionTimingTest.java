package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceTiming;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalLong;
import org.junit.jupiter.api.Test;

/** 执行计时必须来自显式证据，不能从跨夜 call 跨度减工具时间推导。 */
class SessionTimingTest {
  @Test
  void incrementalTimingFinishIsRepeatableAndDoesNotRetainSourceRecords() {
    var accumulator = new SessionTimingCalculator.Accumulator();
    var first = task("main", 0, "", "turn_duration", null, null, 250L);
    accumulator.accept(first);
    accumulator.accept(first);
    var initial = accumulator.finish(2.0);
    assertThat(initial.agentTurnSeconds()).isEqualTo(0.25);
    assertThat(accumulator.finish(2.0)).isEqualTo(initial);

    accumulator.accept(task("main", 1, "", "turn_duration", null, null, 500L));
    var updated = accumulator.finish(2.0);
    assertThat(updated.agentTurnSeconds()).isEqualTo(0.75);
    assertThat(accumulator.finish(2.0)).isEqualTo(updated);
  }

  @Test
  void overnightGapIsWallTimeNotModelOrActiveTaskTime() {
    var first = SourceRecord.of("main#event[0]", 0, "assistant");
    var last = SourceRecord.of("main#event[1]", 1, "assistant");
    NormalizedSessionArtifact artifact =
        normalize(
            List.of(
                timestamped(first, "2026-01-01T00:00:00Z"),
                timestamped(last, "2026-01-02T00:00:00Z")));
    assertThat(artifact.session())
        .containsEntry("duration_seconds", 86400.0)
        .containsEntry("modelExecutionSeconds", 0.0);
    assertThat(timing(artifact))
        .containsEntry("modelExecutionPrecision", "unknown")
        .containsEntry("activeTaskPrecision", "unknown")
        .doesNotContainKey("activeTaskSeconds")
        .doesNotContainKey("modelExecutionSeconds");
  }

  @Test
  void explicitTasksUseProviderDurationRatherThanWriteOutTimestampsAndDeduplicate() {
    SourceRecord start = task("main", 0, "a", "task_started", "2026-01-01T00:00:00Z", null, null);
    SourceRecord end =
        task(
            "main",
            1,
            "a",
            "task_complete",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:10Z",
            10500L);
    SourceRecord aborted =
        task("main", 2, "b", "turn_aborted", "2026-01-02T00:00:00Z", "2026-01-02T00:00:05Z", 5250L);
    Map<String, Object> timing =
        timing(
            normalize(
                List.of(
                    start,
                    start,
                    end,
                    end,
                    task("main", 3, "b", "task_started", "2026-01-02T00:00:00Z", null, null),
                    aborted)));
    assertThat(timing)
        .containsEntry("activeTaskSeconds", 15.75)
        .containsEntry("activeTaskPrecision", "measured")
        .containsEntry("completedTaskCount", 1L)
        .containsEntry("abortedTaskCount", 1L)
        .containsEntry("incompleteTaskCount", 0L)
        .containsEntry("modelExecutionPrecision", "unknown");
  }

  @Test
  void overlappingMainTasksAreUnionedAndParallelChildIsNotAdded() {
    SourceRecord first =
        task("main", 0, "a", "task_complete", "2026-01-01T00:00:00Z", null, 10000L);
    SourceRecord second =
        task("main", 1, "b", "task_complete", "2026-01-01T00:00:05Z", null, 10000L);
    SourceRecord child =
        withChild(task("child", 2, "a", "task_complete", "2026-01-01T00:00:00Z", null, 60000L));
    assertThat(
            timing(
                normalize(
                    List.of(
                        task("main", 3, "a", "task_started", "2026-01-01T00:00:00Z", null, null),
                        first,
                        task("main", 4, "b", "task_started", "2026-01-01T00:00:05Z", null, null),
                        second,
                        child))))
        .containsEntry("activeTaskSeconds", 15.0)
        .containsEntry("completedTaskCount", 2L)
        .containsEntry("activeTaskPrecision", "measured");
  }

  @Test
  void missingIdsOpenTasksAndCrossFileMismatchesArePartialNotGuessed() {
    var valid = task("main", 0, "valid", "task_complete", "2026-01-01T00:00:00Z", null, 1000L);
    var open = task("main", 1, "open", "task_started", "2026-01-01T00:00:03Z", null, null);
    var noId = task("main", 2, "", "task_complete", null, null, null);
    var crossFileStart = task("one", 3, "same", "task_started", "2026-01-01T00:00:05Z", null, null);
    var crossFileEnd = task("two", 4, "same", "task_complete", null, "2026-01-01T00:00:09Z", null);
    assertThat(
            timing(
                normalize(
                    List.of(
                        task(
                            "main", 5, "valid", "task_started", "2026-01-01T00:00:00Z", null, null),
                        valid,
                        open,
                        noId,
                        crossFileStart,
                        crossFileEnd))))
        .containsEntry("activeTaskSeconds", 1.0)
        .containsEntry("activeTaskPrecision", "partial")
        .containsEntry("incompleteTaskCount", 4L);
  }

  @Test
  void measuredZeroIsNotMissingAndNoTaskRecordsStayUnknown() {
    var zero = task("main", 0, "zero", "task_complete", "2026-01-01T00:00:00Z", null, 0L);
    assertThat(
            timing(
                normalize(
                    List.of(
                        task("main", 1, "zero", "task_started", "2026-01-01T00:00:00Z", null, null),
                        zero))))
        .containsEntry("activeTaskSeconds", 0.0)
        .containsEntry("activeTaskPrecision", "measured");
    assertThat(timing(normalize(List.of())))
        .containsEntry("activeTaskPrecision", "unknown")
        .containsEntry("toolExecutionPrecision", "unknown")
        .doesNotContainKey("toolExecutionSeconds");
  }

  @Test
  void selfContainedCompletionWithoutStartIsPartialAndConflictingEndsAreNotChosen() {
    var end =
        task("main", 0, "missing-start", "task_complete", "2026-01-01T00:00:00Z", null, 1000L);
    assertThat(timing(normalize(List.of(end))))
        .containsEntry("activeTaskSeconds", 1.0)
        .containsEntry("activeTaskPrecision", "partial")
        .containsEntry("incompleteTaskCount", 1L);
    var conflicting =
        task("main", 1, "missing-start", "task_complete", "2026-01-01T00:00:00Z", null, 2000L);
    assertThat(timing(normalize(List.of(end, conflicting))))
        .containsEntry("activeTaskPrecision", "unknown")
        .doesNotContainKey("activeTaskSeconds");
  }

  @Test
  void explicitExecutionMeasurementsPreserveRealZeroWithoutUsingTaskDuration() {
    SourceRecord task =
        task("main", 0, "measured", "task_complete", "2026-01-01T00:00:00Z", null, 1000L);
    SourceTiming base = task.timing();
    task =
        task.withTiming(
            new SourceTiming(
                base.kind(),
                base.turnId(),
                base.startedAt(),
                base.completedAt(),
                base.durationMs(),
                OptionalLong.of(0),
                OptionalLong.of(0),
                base.eventId()));
    assertThat(
            timing(
                normalize(
                    List.of(
                        task(
                            "main",
                            1,
                            "measured",
                            "task_started",
                            "2026-01-01T00:00:00Z",
                            null,
                            null),
                        task))))
        .containsEntry("modelExecutionSeconds", 0.0)
        .containsEntry("toolExecutionSeconds", 0.0)
        .containsEntry("modelExecutionPrecision", "measured")
        .containsEntry("toolExecutionPrecision", "measured")
        .containsEntry("activeTaskSeconds", 1.0);
  }

  @Test
  void claudeTurnDurationIsSeparateMainWorkloadNotModelOrTaskWallTime() {
    var main = task("main", 0, "", "turn_duration", null, null, 250L);
    var child = withChild(task("child", 1, "", "turn_duration", null, null, 1000L));
    var artifact =
        new NormalizationEngine()
            .normalize(
                NormalizedAgent.CLAUDE_CODE, List.of(main, main, child), List.of(), List.of());
    assertThat(timing(artifact))
        .containsEntry("agentTurnSeconds", 0.25)
        .containsEntry("agentTurnPrecision", "measured")
        .containsEntry("activeTaskPrecision", "unknown")
        .containsEntry("modelExecutionPrecision", "unknown");
  }

  private static NormalizedSessionArtifact normalize(List<SourceRecord> records) {
    return new NormalizationEngine()
        .normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> timing(NormalizedSessionArtifact artifact) {
    return artifact.session().get("timing") instanceof Map<?, ?> map
        ? (Map<String, Object>) map
        : Map.of();
  }

  private static SourceRecord task(
      String file, int index, String turn, String kind, String start, String end, Long duration) {
    return timestamped(
            SourceRecord.of(file + "#event[" + index + "]", index, "event_msg"),
            "2026-01-03T12:00:00Z")
        .withTiming(
            new SourceTiming(
                kind,
                turn,
                Optional.ofNullable(start),
                Optional.ofNullable(end),
                duration == null ? OptionalLong.empty() : OptionalLong.of(duration),
                OptionalLong.empty(),
                OptionalLong.empty(),
                "event-" + index));
  }

  private static SourceRecord timestamped(SourceRecord record, String timestamp) {
    return new SourceRecord(
        record.locator(),
        record.eventIndex(),
        record.eventType(),
        record.callId(),
        record.model(),
        Optional.of(timestamp),
        record.turnId(),
        record.usage(),
        record.toolCalls(),
        record.toolUseId(),
        record.toolName(),
        record.toolError(),
        record.relation(),
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing());
  }

  private static SourceRecord withChild(SourceRecord record) {
    return new SourceRecord(
        record.locator(),
        record.eventIndex(),
        record.eventType(),
        record.callId(),
        record.model(),
        record.timestamp(),
        record.turnId(),
        record.usage(),
        record.toolCalls(),
        record.toolUseId(),
        record.toolName(),
        record.toolError(),
        new SourceRecordRelation(
            Optional.of("child"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty()),
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing());
  }
}
