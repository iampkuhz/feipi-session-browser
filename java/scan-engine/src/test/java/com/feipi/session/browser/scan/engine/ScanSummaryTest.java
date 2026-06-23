package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/** {@link ScanSummary} 不变量验证测试。 */
class ScanSummaryTest {

  @Test
  void rejectsNegativeCounts() {
    assertThatThrownBy(() -> new ScanSummary(-1, 0, 0, 0, 100, 1, Map.of(), List.of()))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("totalCandidates");
  }

  @Test
  void fullySuccessfulWhenNoErrors() {
    ScanSummary summary = new ScanSummary(5, 5, 0, 0, 100, 1, Map.of(), List.of());
    assertThat(summary.isFullySuccessful()).isTrue();
  }

  @Test
  void notFullySuccessfulWhenHasErrors() {
    ScanSummary summary = new ScanSummary(5, 3, 1, 1, 100, 1, Map.of(), List.of());
    assertThat(summary.isFullySuccessful()).isFalse();
  }

  @Test
  void defensiveCopyOfIssues() {
    java.util.ArrayList<ScanIssue> mutable = new java.util.ArrayList<>();
    mutable.add(new ScanIssue("key1", "claude_code", ScanIssue.ScanPhase.PARSE, "test"));
    ScanSummary summary = new ScanSummary(1, 1, 0, 0, 100, 1, Map.of(), mutable);
    mutable.clear();
    assertThat(summary.issues()).hasSize(1);
  }
}
