package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

/** {@link ScanIssue} 不变量验证测试。 */
class ScanIssueTest {

  @Test
  void rejectsNullFields() {
    assertThatThrownBy(() -> new ScanIssue(null, "claude_code", ScanIssue.ScanPhase.PARSE, "msg"))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new ScanIssue("key", null, ScanIssue.ScanPhase.PARSE, "msg"))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new ScanIssue("key", "claude_code", null, "msg"))
        .isInstanceOf(NullPointerException.class);
    assertThatThrownBy(() -> new ScanIssue("key", "claude_code", ScanIssue.ScanPhase.PARSE, null))
        .isInstanceOf(NullPointerException.class);
  }

  @Test
  void allScanPhasesExist() {
    assertThat(ScanIssue.ScanPhase.values()).hasSize(6);
    assertThat(ScanIssue.ScanPhase.values())
        .containsExactly(
            ScanIssue.ScanPhase.ROOT_CHECK,
            ScanIssue.ScanPhase.DISCOVERY,
            ScanIssue.ScanPhase.PARSE,
            ScanIssue.ScanPhase.NORMALIZE,
            ScanIssue.ScanPhase.ARTIFACT_WRITE,
            ScanIssue.ScanPhase.INDEX_WRITE);
  }
}
