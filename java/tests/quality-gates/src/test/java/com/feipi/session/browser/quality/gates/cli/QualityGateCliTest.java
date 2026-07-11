package com.feipi.session.browser.quality.gates.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/** {@link QualityGateCli} 单元测试。 */
class QualityGateCliTest {

  private static final Path FIXTURE_DIR =
      Path.of("src/test/resources/fixtures/record-component-javadocs");

  @Test
  void missingGateOptionReturnsError() {
    var exitCode = runCli();
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.ERROR);
  }

  @Test
  void unknownGateReturnsError() {
    var exitCode = runCli("--gate", "nonexistent-gate");
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(errOutput()).contains("gate not implemented");
  }

  @Test
  void validFixturesReturnOk() {
    var exitCode =
        runCli(
            "--gate",
            "record-component-javadocs",
            "--paths",
            FIXTURE_DIR.resolve("valid").toString());
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.OK);
  }

  @Test
  void invalidFixturesReturnViolations() {
    var exitCode =
        runCli(
            "--gate",
            "record-component-javadocs",
            "--paths",
            FIXTURE_DIR.resolve("invalid/MissingRecordJavadoc.java").toString());
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(errOutput()).contains("RECORD_JAVADOC_MISSING");
  }

  @Test
  void textOutputFormatMatchesExpected() {
    var exitCode =
        runCli(
            "--gate",
            "record-component-javadocs",
            "--paths",
            FIXTURE_DIR.resolve("invalid/MissingRecordJavadoc.java").toString());
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    // 输出格式为 path:line: CODE: message
    assertThat(errOutput()).matches("(?s).*:\\d+: RECORD_JAVADOC_MISSING:.*");
  }

  @Test
  void jsonOutputFormat() {
    var exitCode =
        runCli(
            "--gate", "record-component-javadocs",
            "--format", "json",
            "--paths", FIXTURE_DIR.resolve("invalid/MissingRecordJavadoc.java").toString());
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(errOutput()).contains("\"code\":\"RECORD_JAVADOC_MISSING\"");
  }

  @Test
  void unknownFormatReturnsError() {
    var exitCode = runCli("--gate", "record-component-javadocs", "--format", "xml");
    assertThat(exitCode).isEqualTo(QualityGateExitCodes.ERROR);
  }

  @Test
  void reportFileWritten() throws Exception {
    var tmpFile = java.nio.file.Files.createTempFile("qg-test-", ".txt");
    try {
      var exitCode =
          runCli(
              "--gate", "record-component-javadocs",
              "--report-file", tmpFile.toString(),
              "--paths", FIXTURE_DIR.resolve("valid/SimpleValidRecord.java").toString());
      assertThat(exitCode).isEqualTo(QualityGateExitCodes.OK);
      var content = java.nio.file.Files.readString(tmpFile, StandardCharsets.UTF_8);
      assertThat(content).contains("PASSED");
    } finally {
      java.nio.file.Files.deleteIfExists(tmpFile);
    }
  }

  // ---- 辅助方法 ----

  private final ByteArrayOutputStream errBuf = new ByteArrayOutputStream();
  private final ByteArrayOutputStream outBuf = new ByteArrayOutputStream();

  private int runCli(String... args) {
    errBuf.reset();
    outBuf.reset();
    var err = new PrintStream(errBuf, true, StandardCharsets.UTF_8);
    var out = new PrintStream(outBuf, true, StandardCharsets.UTF_8);
    return QualityGateCli.run(args, err, out);
  }

  private String errOutput() {
    return errBuf.toString(StandardCharsets.UTF_8);
  }
}
