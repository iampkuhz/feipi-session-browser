package com.feipi.session.browser.source.json;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import org.junit.jupiter.api.Test;

class GenericUsageProvenanceTest {
  @Test
  void explicitZeroIsProviderReportedAndAbsentFieldsAreUnavailable() throws Exception {
    SourceRecordUsage usage = usage("{\"input_tokens\":0,\"outputTokens\":3}");
    assertThat(usage.provenance())
        .containsEntry("freshInputTokenPrecision", "provider_reported")
        .containsEntry("outputTokenPrecision", "provider_reported")
        .containsEntry("cacheReadTokenPrecision", "unavailable")
        .containsEntry("cacheWriteTokenPrecision", "unavailable");
    assertThat(usage.inputTokens()).isZero();
    assertThat(usage.outputTokens()).isEqualTo(3);
  }

  @Test
  void inclusiveCacheAliasKeepsFreshDependencyAndNoUsageStaysUnknown() throws Exception {
    SourceRecordUsage inclusive = usage("{\"input_tokens\":10,\"cached_input_tokens\":4}");
    assertThat(inclusive.inputTokens()).isEqualTo(6);
    assertThat(inclusive.provenance())
        .containsEntry("freshInputTokenPrecision", "provider_reported");
    assertThat(usage("{\"input_tokens\":10,\"cached_input_tokens\":null}").provenance())
        .containsEntry("freshInputTokenPrecision", "unavailable");
    SourceRecordUsage missingInput = usage("{\"cached_input_tokens\":4}");
    assertThat(missingInput.provenance()).containsEntry("freshInputTokenPrecision", "unavailable");
    assertThat(
            JsonSourceRecordMapper.toSourceRecords(
                    "synthetic",
                    0,
                    new ObjectMapper().readTree("{\"type\":\"assistant\"}"),
                    "assistant")
                .getFirst()
                .usage()
                .provenance())
        .isEmpty();
  }

  private static SourceRecordUsage usage(String usage) throws Exception {
    return JsonSourceRecordMapper.toSourceRecords(
            "synthetic",
            0,
            new ObjectMapper().readTree("{\"type\":\"assistant\",\"usage\":" + usage + "}"),
            "assistant")
        .getFirst()
        .usage();
  }
}
