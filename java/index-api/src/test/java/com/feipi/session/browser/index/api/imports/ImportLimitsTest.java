package com.feipi.session.browser.index.api.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** 资源配置不得意外变为无限额。 */
class ImportLimitsTest {
  @Test
  void defaultsAreExplicitAndNonPositiveLimitsAreRejected() {
    assertThat(ImportLimits.defaults())
        .isEqualTo(new ImportLimits(33_554_432, 10_000, 1_000_000, 8, 67_108_864));
    assertThatThrownBy(() -> new ImportLimits(0, 1, 1, 1, 1))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new ImportLimits(1, 0, 1, 1, 1))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new ImportLimits(1, 1, 0, 1, 1))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new ImportLimits(1, 1, 1, 0, 1))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new ImportLimits(1, 1, 1, 1, 0))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
