package com.feipi.session.browser.domain.source;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class SourceRecordUsageProvenanceTest {
  @Test
  void provenanceIsImmutableAndOldConstructorDoesNotInferMeasuredZero() {
    var source = new HashMap<>(Map.of("freshInputTokenPrecision", "provider_reported"));
    var usage = new SourceRecordUsage(0, 0, 0, 0, source);
    source.put("freshInputTokenPrecision", "unknown");
    assertThat(usage.provenance()).containsEntry("freshInputTokenPrecision", "provider_reported");
    assertThatThrownBy(() -> usage.provenance().put("x", "y"))
        .isInstanceOf(UnsupportedOperationException.class);
    assertThat(new SourceRecordUsage(0, 0, 0, 0).provenance()).isEmpty();
    assertThat(new SourceRecordUsage(1, 2, 3, 4).provenance()).isEmpty();
    assertThatThrownBy(() -> new SourceRecordUsage(-1, 0, 0, 0, Map.of()))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new SourceRecordUsage(0, 0, 0, 0, null))
        .isInstanceOf(NullPointerException.class);
  }
}
