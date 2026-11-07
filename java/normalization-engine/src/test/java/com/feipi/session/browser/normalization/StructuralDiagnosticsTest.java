package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

/** 大型合法结构与真正未知事件的诊断必须完整且可定位。 */
class StructuralDiagnosticsTest {
  @Test
  void repeatedUnknownSubtypeRetainsExactCoverageWithoutExceedingArtifactLimit() {
    var records =
        IntStream.range(0, 10_001)
            .mapToObj(index -> record(index, "event_msg", "item_completed"))
            .toList();
    var artifact =
        new NormalizationEngine().normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    assertThat(artifact.session()).containsEntry("eventCount", 10_001);
    assertThat(artifact.diagnostics())
        .singleElement()
        .satisfies(
            diagnostic -> {
              assertThat(diagnostic)
                  .containsEntry("severity", "WARNING")
                  .containsEntry("occurrenceCount", 10_001)
                  .containsEntry("firstEventIndex", 0)
                  .containsEntry("lastEventIndex", 10_000)
                  .containsEntry("firstLocator", "synthetic.jsonl#event[0]")
                  .containsEntry("lastLocator", "synthetic.jsonl#event[10000]");
            });
  }

  @Test
  void knownCodexStructuresDoNotProduceUnknownWarningsOrLoseEvents() {
    var records =
        IntStream.range(0, 10_001)
            .mapToObj(index -> record(index, index % 2 == 0 ? "session_meta" : "turn_context", ""))
            .toList();
    var artifact =
        new NormalizationEngine().normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    assertThat(artifact.diagnostics()).isEmpty();
    assertThat(artifact.session()).containsEntry("eventCount", 10_001);
    assertThat(EventClassifier.classify(records).allEvents()).containsExactlyElementsOf(records);
    var otherAgent =
        new NormalizationEngine()
            .normalize(
                NormalizedAgent.CLAUDE_CODE, List.of(records.getFirst()), List.of(), List.of());
    assertThat(otherAgent.diagnostics()).hasSize(1);
  }

  @Test
  void wrappersWithoutSubtypeRemainUnknownAndGroupsDoNotCrossSourcesOrSubtypes() {
    var records =
        List.of(
            record(2, "response_item", ""),
            record(4, "response_item", ""),
            record(5, "event_msg", "unknown_one"),
            record(6, "event_msg", "unknown_two"),
            SourceRecord.of("other.jsonl#event[1]", 1, "response_item"));
    var artifact =
        new NormalizationEngine().normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    assertThat(artifact.diagnostics()).hasSize(4);
    assertThat(artifact.diagnostics().getFirst())
        .containsEntry("occurrenceCount", 2)
        .containsEntry("firstEventIndex", 2)
        .containsEntry("lastEventIndex", 4);
    assertThat(artifact.session().get("unknownEventDiagnosticCoverage"))
        .isEqualTo(
            java.util.Map.of(
                "occurrences",
                5L,
                "groups",
                4,
                "grouping",
                "sourceLocator,eventType,eventMsgSubtype",
                "positionUnit",
                "sourceEventIndex"));
  }

  @Test
  void parserDiagnosticsAndCallContentRemainUnchangedByUnknownAggregation() {
    var input =
        new SourceDiagnostic(
            ParseSeverity.ERROR,
            ParseIssueType.BAD_JSON,
            "synthetic parse failure",
            17,
            Optional.empty(),
            "BAD_JSON",
            "synthetic.jsonl",
            OptionalInt.of(3),
            OptionalInt.of(40),
            OptionalInt.of(41));
    var user =
        SourceRecord.of("synthetic.jsonl#event[1]", 1, "user").withContent("synthetic prompt");
    var assistant =
        SourceRecord.of("synthetic.jsonl#event[2]", 2, "assistant").withContent("synthetic answer");
    var engine = new NormalizationEngine();
    var baseline =
        engine.normalize(
            NormalizedAgent.CODEX, List.of(user, assistant), List.of(input, input), List.of());
    var changed =
        engine.normalize(
            NormalizedAgent.CODEX,
            List.of(user, record(3, "world_state", ""), assistant, record(4, "world_state", "")),
            List.of(input, input),
            List.of());
    assertThat(changed.calls()).isEqualTo(baseline.calls());
    assertThat(changed.session().get("totalTokens"))
        .isEqualTo(baseline.session().get("totalTokens"));
    assertThat(changed.diagnostics()).hasSize(3);
    assertThat(changed.diagnostics().subList(0, 2)).isEqualTo(baseline.diagnostics());
    assertThat(changed.diagnostics().getFirst())
        .containsEntry("lineNo", 17)
        .containsEntry("column", 3)
        .containsEntry("byteRangeStart", 40)
        .containsEntry("byteRangeEnd", 41);
    assertThat(changed.diagnostics().getLast()).containsEntry("occurrenceCount", 2);
  }

  private static SourceRecord record(int index, String type, String subtype) {
    return new SourceRecord(
        "synthetic.jsonl#event[" + index + "]",
        index,
        type,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        Optional.of(subtype),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty());
  }
}
