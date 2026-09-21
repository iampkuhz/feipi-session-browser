package com.feipi.session.browser.domain.source;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class SourceRecordTest {

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
