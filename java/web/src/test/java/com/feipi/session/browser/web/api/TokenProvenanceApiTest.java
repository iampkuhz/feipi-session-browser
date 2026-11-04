package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.web.api.DashboardApiResponses.CacheInputDto;
import com.feipi.session.browser.web.api.DashboardApiResponses.RatioDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import org.junit.jupiter.api.Test;

class TokenProvenanceApiTest {

  private static final TokenProvenance REPORTED =
      new TokenProvenance(
          "provider_reported",
          "provider_reported",
          "provider_reported",
          "provider_reported",
          "",
          0,
          0,
          0);
  private static final TokenProvenance ESTIMATED =
      new TokenProvenance(
          "estimated",
          "unavailable",
          "unavailable",
          "estimated",
          "synthetic_context_estimate",
          1,
          1,
          0);

  @Test
  void keepsNumericContractAndAddsSameScopeEvidence() throws Exception {
    var json = new ObjectMapper().valueToTree(TokenSegments.of(17, 31, 5, 9, REPORTED));
    assertThat(json.path("fresh").asLong()).isEqualTo(17);
    assertThat(json.path("cacheRead").asLong()).isEqualTo(31);
    assertThat(json.path("cacheWrite").asLong()).isEqualTo(5);
    assertThat(json.path("output").asLong()).isEqualTo(9);
    assertThat(json.path("total").asLong()).isEqualTo(62);
    assertThat(json.at("/provenance/freshInput").asText()).isEqualTo("provider_reported");
  }

  @Test
  void absentEvidenceDoesNotBecomeReportedZero() {
    var tokens = new TokenSegments(0, 0, 0, 0, 0);
    assertThat(tokens.provenance().freshInput()).isEqualTo("unknown");
    assertThat(tokens.provenance().unknownSessionCount()).isEqualTo(1);
    assertThat(RatioDto.of(0.0, tokens.provenance()).value()).isNull();
    assertThat(RatioDto.of(0.0, tokens.provenance()).reason())
        .isEqualTo("token_measurement_unknown");
  }

  @Test
  void reportedZeroIsDistinctFromMissingCache() {
    var zero = CacheInputDto.of(11, 0, 0, REPORTED);
    assertThat(zero.ratio().value()).isZero();
    assertThat(zero.ratio().reason()).isEmpty();
    var unavailable = CacheInputDto.of(11, 0, 0, ESTIMATED);
    assertThat(unavailable.ratio().value()).isNull();
    assertThat(unavailable.ratio().reason()).isEqualTo("token_measurement_unavailable");
    assertThat(unavailable.provenance()).isEqualTo(ESTIMATED);
  }

  @Test
  void mixedAggregateKeepsCoverageAndMarksPartialRatio() {
    var mixed = REPORTED.plus(ESTIMATED).plus(TokenProvenance.unknown());
    var ratio = RatioDto.of(0.4, mixed);
    assertThat(ratio.value()).isEqualTo(0.4);
    assertThat(ratio.reason()).isEqualTo("partial_token_measurement");
    assertThat(ratio.provenance().estimatedSessionCount()).isEqualTo(1);
    assertThat(ratio.provenance().unavailableSessionCount()).isEqualTo(1);
    assertThat(ratio.provenance().unknownSessionCount()).isEqualTo(1);
  }

  @Test
  void emptyMergeDoesNotAddUnknownSessions() {
    var tokens = TokenSegments.of(0, 0, 0, 0, TokenProvenance.empty());
    assertThat(tokens.provenance().unknownSessionCount()).isZero();
    assertThat(TokenProvenance.empty().plus(REPORTED)).isEqualTo(REPORTED);
    assertThat(RatioDto.of(null, TokenProvenance.empty()).reason())
        .isEqualTo("no_eligible_input_tokens");
  }
}
