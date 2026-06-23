package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.SourceId;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * {@link IncrementalScanSummary} 单元测试。
 *
 * <p>验证 record 不变量、工厂方法和字段拷贝。
 */
class IncrementalScanSummaryTest {

  @Test
  void validSummaryConstruction() {
    IncrementalScanSummary summary =
        new IncrementalScanSummary(10, 5, 2, 1, 1000, 1, Map.of(), List.of(), 3, 4, 2, 1, false);

    assertThat(summary.totalCandidates()).isEqualTo(10);
    assertThat(summary.successCount()).isEqualTo(5);
    assertThat(summary.skippedCount()).isEqualTo(2);
    assertThat(summary.errorCount()).isEqualTo(1);
    assertThat(summary.unchangedCount()).isEqualTo(3);
    assertThat(summary.changedCount()).isEqualTo(4);
    assertThat(summary.newCount()).isEqualTo(2);
    assertThat(summary.retryableCount()).isEqualTo(1);
    assertThat(summary.rebuildTriggered()).isFalse();
  }

  @Test
  void negativeCountsRejected() {
    assertThatThrownBy(
            () ->
                new IncrementalScanSummary(
                    -1, 0, 0, 0, 0, 0, Map.of(), List.of(), 0, 0, 0, 0, false))
        .isInstanceOf(IllegalArgumentException.class);

    assertThatThrownBy(
            () ->
                new IncrementalScanSummary(
                    0, -1, 0, 0, 0, 0, Map.of(), List.of(), 0, 0, 0, 0, false))
        .isInstanceOf(IllegalArgumentException.class);

    assertThatThrownBy(
            () ->
                new IncrementalScanSummary(
                    0, 0, 0, 0, 0, 0, Map.of(), List.of(), -1, 0, 0, 0, false))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void fromBaseFactoryMethod() {
    ScanSummary base =
        new ScanSummary(10, 5, 2, 1, 1000, 1, Map.of(SourceId.CLAUDE_CODE, 10), List.of());

    IncrementalScanSummary summary = IncrementalScanSummary.fromBase(base, 3, 4, 2, 1, true);

    assertThat(summary.totalCandidates()).isEqualTo(10);
    assertThat(summary.successCount()).isEqualTo(5);
    assertThat(summary.unchangedCount()).isEqualTo(3);
    assertThat(summary.changedCount()).isEqualTo(4);
    assertThat(summary.newCount()).isEqualTo(2);
    assertThat(summary.retryableCount()).isEqualTo(1);
    assertThat(summary.rebuildTriggered()).isTrue();
    assertThat(summary.perSourceCount()).containsEntry(SourceId.CLAUDE_CODE, 10);
  }

  @Test
  void defensiveCopyOfCollections() {
    IncrementalScanSummary summary =
        new IncrementalScanSummary(0, 0, 0, 0, 0, 0, Map.of(), List.of(), 0, 0, 0, 0, false);

    assertThat(summary.issues()).isEmpty();
    assertThat(summary.perSourceCount()).isEmpty();
  }
}
