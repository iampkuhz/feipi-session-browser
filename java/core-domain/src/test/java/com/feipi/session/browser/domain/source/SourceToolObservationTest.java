package com.feipi.session.browser.domain.source;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 精确观测及其摘要的领域不变量。 */
class SourceToolObservationTest {
  @Test
  void unknownZeroAndSubmillisecondAreDistinctAndCopiesPreserveObservation() {
    for (Long duration : new Long[] {null, 0L, 1L, Long.MAX_VALUE}) {
      var observation = value(duration);
      assertThat(observation.durationMs())
          .isEqualTo(duration == null ? null : duration / 1_000_000);
      var record =
          SourceRecord.of("synthetic", 0, "event_msg")
              .withToolObservation(Optional.of(observation));
      assertThat(
              record
                  .withContent("body")
                  .withTiming(SourceTiming.empty())
                  .withMessageRole(Optional.empty())
                  .toolObservation())
          .contains(observation);
      assertThat(observation.toString()).doesNotContain("private-process", "event[123]");
      var tool =
          new NormalizedToolExecution(
              "tool",
              "exec_command",
              CallScope.MAIN,
              "call",
              Optional.empty(),
              Optional.empty(),
              Optional.of(0),
              observation.durationMs(),
              List.of(),
              Optional.empty(),
              Optional.of(observation));
      assertThat(tool.durationMs()).isEqualTo(observation.durationMs());
    }
  }

  @Test
  void negativeDurationAndInconsistentProjectionAreRejected() {
    assertThatThrownBy(() -> value(-1L)).isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                new NormalizedToolExecution(
                    "wrong-tool",
                    "exec_command",
                    CallScope.MAIN,
                    "call",
                    Optional.empty(),
                    Optional.empty(),
                    Optional.of(0),
                    0L,
                    List.of(),
                    Optional.empty(),
                    Optional.of(value(0L))))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private static SourceToolObservation value(Long duration) {
    return new SourceToolObservation(
        "tool",
        duration,
        0,
        "completed",
        "private-process",
        "executor_reported",
        "codex:exec_command_end#event[123]",
        null);
  }
}
