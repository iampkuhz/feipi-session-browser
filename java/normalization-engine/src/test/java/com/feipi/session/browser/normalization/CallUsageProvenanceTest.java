package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class CallUsageProvenanceTest {
  @Test
  void eachCallRetainsOnlyItsOwnExplicitUsageEvidenceIncludingRealZero() {
    Map<String, String> provider =
        Map.of(
            "freshInputTokenPrecision",
            "provider_reported",
            "outputTokenPrecision",
            "provider_reported");
    Map<String, String> partial =
        Map.of("freshInputTokenPrecision", "unavailable", "outputTokenPrecision", "unknown");
    var artifact =
        new NormalizationEngine()
            .normalize(
                NormalizedAgent.CODEX,
                List.of(
                    record(0, "first", new SourceRecordUsage(0, 0, 0, 5, provider)),
                    record(1, "second", new SourceRecordUsage(0, 0, 0, 0, partial)),
                    record(2, "legacy", SourceRecordUsage.empty())),
                List.of(),
                List.of());
    assertThat(artifact.calls()).hasSize(3);
    assertThat(artifact.calls().get(0).usageSource()).containsExactlyInAnyOrderEntriesOf(provider);
    assertThat(artifact.calls().get(0).usage().fresh()).isZero();
    assertThat(artifact.calls().get(1).usageSource()).containsExactlyInAnyOrderEntriesOf(partial);
    assertThat(artifact.calls().get(2).usageSource()).isEmpty();
    assertThat(TokenProvenance.fromMetadata(artifact.calls().get(2).usageSource()).freshInput())
        .isEqualTo("unknown");
  }

  @Test
  void qoderMaxMergeKeepsComponentEvidenceAndDoesNotLetEmptyZeroEraseMeasuredZero() {
    var first =
        record(
            0,
            "shared",
            new SourceRecordUsage(
                0,
                0,
                0,
                7,
                Map.of(
                    "freshInputTokenPrecision",
                    "provider_reported",
                    "outputTokenPrecision",
                    "estimated")));
    var second =
        record(
            1,
            "shared",
            new SourceRecordUsage(0, 0, 0, 9, Map.of("outputTokenPrecision", "provider_reported")));
    var empty = record(2, "shared", SourceRecordUsage.empty());
    var artifact =
        new NormalizationEngine()
            .normalize(NormalizedAgent.QODER, List.of(first, second, empty), List.of(), List.of());
    assertThat(artifact.calls()).hasSize(1);
    var call = artifact.calls().getFirst();
    assertThat(call.usage().output()).isEqualTo(9);
    assertThat(call.usageSource())
        .containsEntry("freshInputTokenPrecision", "provider_reported")
        .containsEntry("outputTokenPrecision", "provider_reported")
        .containsEntry("cacheReadTokenPrecision", "unknown");
  }

  @Test
  void qoderEqualPositiveEvidenceConflictRemainsMixedAndClaudeRetainsAdjudicatedUsage() {
    var first =
        record(
            0,
            "shared",
            new SourceRecordUsage(
                3, 0, 0, 0, Map.of("freshInputTokenPrecision", "provider_reported")));
    var second = record(1, "shared", new SourceRecordUsage(3, 0, 0, 0));
    var qoder =
        new NormalizationEngine()
            .normalize(NormalizedAgent.QODER, List.of(first, second), List.of(), List.of());
    assertThat(qoder.calls().getFirst().usageSource())
        .containsEntry("freshInputTokenPrecision", "mixed");
    var claude =
        new NormalizationEngine()
            .normalize(NormalizedAgent.CLAUDE_CODE, List.of(first, second), List.of(), List.of());
    assertThat(claude.calls()).hasSize(1);
    assertThat(claude.calls().getFirst().usageSource())
        .containsExactlyInAnyOrderEntriesOf(first.usage().provenance());
  }

  private static SourceRecord record(int index, String response, SourceRecordUsage usage) {
    return new SourceRecord(
        "synthetic.jsonl#event[" + index + "]",
        index,
        "assistant",
        Optional.of("token_count:" + response),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        usage,
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        SourceRecordRelation.empty(),
        "synthetic response",
        Optional.of(response),
        Optional.empty(),
        SourceTiming.empty(),
        false);
  }
}
