package com.feipi.session.browser.domain.source;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;

class SourceRecordSequenceTest {
  @Test
  void immutableListSupportsIndependentReplayAndOrdinalSeek() throws Exception {
    var first = SourceRecord.of("synthetic.jsonl", 7, "unknown");
    var second = SourceRecord.of("synthetic.jsonl", 7, "unknown").withContent("second");
    var input = new ArrayList<>(List.of(first, second));
    try (var sequence = SourceRecordSequence.fromList(input)) {
      input.clear();
      assertThat(sequence.recordCount()).isEqualTo(2);
      for (int replay = 0; replay < 2; replay++) {
        try (var cursor = sequence.openCursor();
            var other = sequence.openCursor(1)) {
          assertThat(cursor.next()).isSameAs(first);
          assertThat(other.next()).isSameAs(second);
          assertThat(cursor.next()).isSameAs(second);
          assertThat(cursor.hasNext()).isFalse();
          assertThat(other.hasNext()).isFalse();
          assertThatThrownBy(cursor::next).isInstanceOf(NoSuchElementException.class);
        }
      }
      try (var end = sequence.openCursor(sequence.recordCount())) {
        assertThat(end.hasNext()).isFalse();
        assertThatThrownBy(end::next).isInstanceOf(NoSuchElementException.class);
      }
      assertThatThrownBy(() -> sequence.openCursor(-1))
          .isInstanceOf(IllegalArgumentException.class);
      assertThatThrownBy(() -> sequence.openCursor(3)).isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void cursorCloseDoesNotCloseOwnerButOwnerCloseRejectsAllReads() throws Exception {
    var sequence =
        SourceRecordSequence.fromList(List.of(SourceRecord.of("synthetic", 0, "unknown")));
    var cursor = sequence.openCursor();
    cursor.close();
    cursor.close();
    assertThatThrownBy(cursor::hasNext).isInstanceOf(IOException.class);
    assertThatThrownBy(cursor::next).isInstanceOf(IOException.class);
    var active = sequence.openCursor();
    assertThat(active.hasNext()).isTrue();
    sequence.close();
    sequence.close();
    assertThatThrownBy(active::hasNext).isInstanceOf(IOException.class);
    assertThatThrownBy(active::next).isInstanceOf(IOException.class);
    assertThatThrownBy(sequence::openCursor).isInstanceOf(IOException.class);
    assertThatThrownBy(() -> sequence.openCursor(0)).isInstanceOf(IOException.class);
    active.close();
  }

  @Test
  void emptyListIsReplayableAndNullElementsAreRejected() throws Exception {
    try (var sequence = SourceRecordSequence.fromList(List.of());
        var cursor = sequence.openCursor()) {
      assertThat(sequence.recordCount()).isZero();
      assertThat(cursor.hasNext()).isFalse();
      assertThatThrownBy(cursor::next).isInstanceOf(NoSuchElementException.class);
    }
    assertThatThrownBy(() -> SourceRecordSequence.fromList(null))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(
            () -> SourceRecordSequence.fromList(java.util.Collections.singletonList(null)))
        .isInstanceOf(NullPointerException.class);
  }
}
