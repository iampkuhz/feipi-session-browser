package com.feipi.session.browser.domain.source;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;
import org.junit.jupiter.api.Test;

class SourceRecordTest {

  @Test
  void metaContextAndTimingSurviveContentAndTimingCopies() {
    SourceTiming timing =
        new SourceTiming(
            "turn_duration",
            "synthetic-turn",
            Optional.empty(),
            Optional.empty(),
            OptionalLong.of(19),
            OptionalLong.of(0),
            OptionalLong.empty(),
            "synthetic-event");
    SourceRecord record =
        new SourceRecord(
            "synthetic.jsonl#event[0]",
            0,
            "user",
            Optional.of("synthetic-call"),
            Optional.of("synthetic-model"),
            Optional.of("synthetic-time"),
            Optional.of("synthetic-turn"),
            new SourceRecordUsage(1, 2, 3, 4),
            List.of(new SourceToolCall("synthetic-tool", "Read", "{}")),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordRelation.empty(),
            "  synthetic meta context\n",
            Optional.of("synthetic-message"),
            Optional.of("end_turn"),
            timing,
            true);

    assertThat(record.metaContext()).isTrue();
    SourceRecord contentCopy = record.withContent("replacement");
    assertThat(contentCopy).usingRecursiveComparison().ignoringFields("content").isEqualTo(record);
    assertThat(contentCopy.content()).isEqualTo("replacement");
    SourceRecord timingCopy = record.withTiming(SourceTiming.empty());
    assertThat(timingCopy).usingRecursiveComparison().ignoringFields("timing").isEqualTo(record);
    assertThat(timingCopy.timing()).isEqualTo(SourceTiming.empty());
    assertThat(record.toString()).doesNotContain("synthetic", "context", "message", "model");
  }

  @Test
  void legacyContentAndTimingConstructorsDefaultMetaContextToFalse() {
    SourceTiming timing =
        new SourceTiming(
            "turn_duration",
            "synthetic-turn",
            Optional.empty(),
            Optional.empty(),
            OptionalLong.of(0),
            OptionalLong.empty(),
            OptionalLong.empty(),
            "synthetic-zero");
    SourceRecord contentRecord =
        new SourceRecord(
            "synthetic.jsonl",
            0,
            "user",
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
            "context");
    SourceRecord timingRecord =
        new SourceRecord(
            "synthetic.jsonl",
            0,
            "user",
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
            "context",
            Optional.empty(),
            Optional.empty(),
            timing);
    assertThat(contentRecord.metaContext()).isFalse();
    assertThat(timingRecord.metaContext()).isFalse();
    assertThat(timingRecord.timing()).isEqualTo(timing);
    assertThat(SourceRecord.of("synthetic.jsonl", 0, "user").metaContext()).isFalse();
  }

  @Test
  void legacyRelationConstructorAndContentCopyPreserveFields() {
    SourceRecordRelation relation =
        new SourceRecordRelation(
            Optional.of("child"),
            Optional.of("parent"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    SourceRecord record =
        new SourceRecord(
            "synthetic.jsonl#event[2]",
            2,
            "assistant",
            Optional.of("call"),
            Optional.of("model"),
            Optional.of("time"),
            Optional.of("turn"),
            new SourceRecordUsage(1, 2, 3, 4),
            List.of(new SourceToolCall("tool", "Read")),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            relation);
    assertThat(record.content()).isEmpty();
    assertThat(record.metaContext()).isFalse();
    SourceRecord copy = record.withContent("  synthetic private content\n");
    assertThat(copy.content()).isEqualTo("  synthetic private content\n");
    assertThat(copy.withContent("")).isEqualTo(record);
    assertThat(copy.withContent(null)).isEqualTo(record);
    assertThat(copy.relation()).isEqualTo(relation);
    assertThat(copy.toString()).doesNotContain("synthetic", "private", "parent", "child", "model");
  }

  @Test
  void legacyConstructorWithoutRelationStillDefaultsToEmptyContent() {
    SourceRecord record =
        new SourceRecord(
            "synthetic.jsonl",
            0,
            "user",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    assertThat(record.content()).isEmpty();
    assertThat(record.relation()).isEqualTo(SourceRecordRelation.empty());
    assertThat(record.metaContext()).isFalse();
    assertThat(record.responseMessageId()).isEmpty();
    assertThat(record.responseStopReason()).isEmpty();
  }

  @Test
  void canonicalConstructorPreservesResponseMetadata() {
    SourceRecord record =
        new SourceRecord(
            "synthetic.jsonl#event[0]",
            0,
            "assistant",
            Optional.of("call-1"),
            Optional.of("model"),
            Optional.of("time"),
            Optional.of("turn"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordRelation.empty(),
            "content",
            Optional.of("msg-123"),
            Optional.of("end_turn"));
    assertThat(record.responseMessageId()).contains("msg-123");
    assertThat(record.responseStopReason()).contains("end_turn");
    assertThat(record.metaContext()).isFalse();
  }

  @Test
  void withContentPreservesResponseMetadata() {
    SourceRecord record =
        new SourceRecord(
            "synthetic.jsonl#event[0]",
            0,
            "assistant",
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
            "original",
            Optional.of("msg-456"),
            Optional.of("tool_use"));
    SourceRecord copy = record.withContent("replaced");
    assertThat(copy.content()).isEqualTo("replaced");
    assertThat(copy.responseMessageId()).contains("msg-456");
    assertThat(copy.responseStopReason()).contains("tool_use");
  }

  @Test
  void nullResponseMetadataDefaultsToEmpty() {
    SourceRecord record =
        new SourceRecord(
            "synthetic.jsonl#event[0]",
            0,
            "assistant",
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
            "",
            null,
            null);
    assertThat(record.responseMessageId()).isEmpty();
    assertThat(record.responseStopReason()).isEmpty();
  }
}
