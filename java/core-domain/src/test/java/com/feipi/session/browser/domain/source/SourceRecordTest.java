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
  }
}
