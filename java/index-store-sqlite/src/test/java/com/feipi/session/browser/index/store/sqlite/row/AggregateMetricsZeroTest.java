package com.feipi.session.browser.index.store.sqlite.row;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class AggregateMetricsZeroTest {
  @ParameterizedTest
  @ValueSource(ints = {1, 2, 4, 3})
  void positiveDenominatorPreservesMeasuredZero(int scale) {
    assertThat(AggregateMetricsRow.safeDivRound(0, 10, scale)).isEqualTo(0.0);
  }

  @ParameterizedTest
  @ValueSource(longs = {0, -1})
  void invalidDenominatorRemainsUnknown(long denominator) {
    assertThat(AggregateMetricsRow.safeDivRound(0, denominator, 4)).isNull();
    assertThat(AggregateMetricsRow.safeDivRound(10, denominator, 4)).isNull();
  }
}
