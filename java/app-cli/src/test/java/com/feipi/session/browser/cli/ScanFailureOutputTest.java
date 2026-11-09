package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.scan.engine.ScanIssue;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;

class ScanFailureOutputTest {
  @Test
  void cliPrintsSafeCodesAndRetryGuidanceNotRawMessagesOrSessionIdentity() throws Exception {
    var output = new ByteArrayOutputStream();
    var original = System.err;
    try (var stream = new PrintStream(output, true, StandardCharsets.UTF_8)) {
      System.setErr(stream);
      var method = ScanCommand.class.getDeclaredMethod("printFailures", long.class, List.class);
      method.setAccessible(true);
      method.invoke(
          null,
          17L,
          List.of(
              new ScanIssue(
                  "fixture-private-session",
                  "codex",
                  ScanIssue.ScanPhase.PARSE,
                  "SOURCE_ERRORS:BUFFER_OVERFLOW@42",
                  "CODEX_HISTORY_PARENT_CONFLICT"),
              new ScanIssue(
                  "fixture-private-session",
                  "codex",
                  ScanIssue.ScanPhase.NORMALIZE,
                  "fixture-sensitive-message calls size exceeds limit 10000")));
    } finally {
      System.setErr(original);
    }
    assertThat(output.toString(StandardCharsets.UTF_8))
        .contains(
            "BUFFER_OVERFLOW",
            "42",
            "scanLogId=17",
            "code=CODEX_HISTORY_PARENT_CONFLICT",
            "hint[CODEX_HISTORY_PARENT_CONFLICT]",
            "NORMALIZED_CALL_LIMIT_EXCEEDED",
            "No partial results",
            "Retry")
        .doesNotContain("fixture-private-session", "fixture-sensitive-message");
  }
}
