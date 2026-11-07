package com.feipi.session.browser.source.spi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.source.SourceRecordSequence;
import java.io.IOException;
import java.util.List;
import org.junit.jupiter.api.Test;

class ManagedSourceResultTest {
  @Test
  void managedConstructionAndAccessNeverOpenOrMaterializeRecords() throws Exception {
    var sequence = new TrapSequence();
    var result = SourceResult.Success.managed(List.of(), 1, sequence, null, "synthetic");
    assertThat(result.hasManagedRecords()).isTrue();
    assertThat(result.recordSequence()).isSameAs(sequence);
    assertThat(sequence.openCount).isZero();
    assertThatThrownBy(result::records)
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("recordSequence()");
    assertThatThrownBy(() -> result.recordSequence().openCursor())
        .isInstanceOf(IOException.class)
        .hasMessage("synthetic read failure");
    assertThat(sequence.openCount).isEqualTo(1);
    assertThat(result.toString()).contains("managed");
    result.close();
    result.close();
    assertThat(sequence.closeCount).isEqualTo(1);
  }

  @Test
  void legacySequenceUsesSameImmutableRecordsAndCloseRejectsReading() throws Exception {
    var result = new SourceResult.Success(List.of(), 0, null, null, null);
    assertThat(result.hasManagedRecords()).isFalse();
    assertThat(result.records()).isEmpty();
    assertThat(result.recordSequence()).isSameAs(result.recordSequence());
    var cursor = result.recordSequence().openCursor();
    assertThat(cursor.hasNext()).isFalse();
    result.close();
    assertThatThrownBy(cursor::hasNext).isInstanceOf(IOException.class);
    assertThatThrownBy(result.recordSequence()::openCursor).isInstanceOf(IOException.class);
    cursor.close();
  }

  @Test
  void invalidManagedConstructionDoesNotTakeSequenceOwnership() {
    var sequence = new TrapSequence();
    assertThatThrownBy(() -> SourceResult.Success.managed(List.of(), -1, sequence, null, null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("candidateCount");
    assertThatThrownBy(() -> SourceResult.Success.managed(List.of(), 0, null, null, null))
        .isInstanceOf(NullPointerException.class);
    assertThat(sequence.openCount).isZero();
    assertThat(sequence.closeCount).isZero();
  }

  @Test
  void closeFailureIsNotSwallowedAndRepeatedCloseIsIdempotent() throws Exception {
    var sequence = new TrapSequence();
    sequence.failClose = true;
    var result = SourceResult.Success.managed(List.of(), 0, sequence, null, null);
    assertThatThrownBy(result::close)
        .isInstanceOf(IOException.class)
        .hasMessage("synthetic close failure");
    result.close();
    assertThat(sequence.closeCount).isEqualTo(1);
  }

  private static final class TrapSequence implements SourceRecordSequence {
    private int openCount;
    private int closeCount;
    private boolean failClose;

    @Override
    public long recordCount() {
      return 1;
    }

    @Override
    public RecordCursor openCursor() throws IOException {
      return openCursor(0);
    }

    @Override
    public RecordCursor openCursor(long ordinal) throws IOException {
      openCount++;
      throw new IOException("synthetic read failure");
    }

    @Override
    public void close() throws IOException {
      closeCount++;
      if (failClose) {
        throw new IOException("synthetic close failure");
      }
    }
  }
}
