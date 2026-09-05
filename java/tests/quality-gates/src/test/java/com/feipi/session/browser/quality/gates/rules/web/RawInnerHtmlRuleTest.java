package com.feipi.session.browser.quality.gates.rules.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.quality.gates.cli.QualityGateCli;
import com.feipi.session.browser.quality.gates.cli.QualityGateExitCodes;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** raw-innerHTML 的逐行匹配、扫描范围、baseline 与诊断长度 corpus。 */
class RawInnerHtmlRuleTest {

  private static final String BASELINE =
      "java/tests/quality-gates/config/web-quality-baselines.json";
  private static final String STATIC_JS = "java/web/src/main/resources/static/js";

  @TempDir Path repo;

  @BeforeEach
  void createEmptyBaseline() throws Exception {
    writeBaseline("[]");
  }

  @Test
  void reportsClearEscapedAndPurifiedAssignmentsButSkipsReadsAndCommentLines() throws Exception {
    write(
        STATIC_JS + "/boundaries.js",
        """
        const current = node.innerHTML;
        // node.innerHTML = value;
        /* node.innerHTML = value; */
         * node.innerHTML = value;
        node.innerHTML = '';
        escaped.innerHTML = escapeHtml(value);
        purified.innerHTML = DOMPurify.sanitize(value);
        regular.innerHTML   = value;
        """);

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.err()).isEmpty();
    assertThat(result.out())
        .contains("\"violationCount\":4")
        .contains("RAW_INNERHTML_NEW")
        .contains("\"isClear\":\"true\"")
        .contains("escapeHtml(value)")
        .contains("DOMPurify.sanitize(value)")
        .contains("textContent 或 escapeHtml()")
        .contains("只有经审阅后才可显式更新 baseline");
  }

  @Test
  void keepsPythonUnicodeWhitespaceAndSplitlinesSemantics() throws Exception {
    var nonBreakingSpace = Character.toString(0x00A0);
    var nextLine = Character.toString(0x0085);
    var lineSeparator = Character.toString(0x2028);
    var paragraphSeparator = Character.toString(0x2029);
    var verticalTab = Character.toString(0x000B);
    var formFeed = Character.toString(0x000C);
    write(
        STATIC_JS + "/unicode-lines.js",
        nonBreakingSpace
            + "// ignored.innerHTML = value;"
            + lineSeparator
            + "node.innerHTML"
            + nonBreakingSpace
            + "= value;"
            + nextLine
            + "clear.innerHTML ="
            + nonBreakingSpace
            + "'';"
            + verticalTab
            + "third.innerHTML = value;"
            + formFeed
            + "fourth.innerHTML = value;"
            + paragraphSeparator
            + "fifth.innerHTML = value;");

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"violationCount\":5")
        .contains("\"line\":2")
        .contains("\"line\":6")
        .contains("\"isClear\":\"true\"")
        .doesNotContain("ignored.innerHTML");
  }

  @Test
  void scansStaticJsTestsAndScriptsWithoutChangedFileNarrowing() throws Exception {
    write(STATIC_JS + "/nested/main.js", "main.innerHTML = value;\n");
    write("tests/generated/browser.js", "test.innerHTML = value;\n");
    write("scripts/tmp/tool.js", "tool.innerHTML = value;\n");
    write(
        "java/web/src/main/resources/static/generated/outside.js", "outside.innerHTML = value;\n");

    var result = run("[\"java/web/src/main/resources/static/generated/outside.js\"]");

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"violationCount\":3")
        .contains("nested/main.js")
        .contains("tests/generated/browser.js")
        .contains("scripts/tmp/tool.js")
        .doesNotContain("static/generated/outside.js");
  }

  @Test
  void baselineUsesOnlyTheExactFileAndLineAndMalformedBaselineFailsClosed() throws Exception {
    var relative = STATIC_JS + "/known.js";
    write(relative, "known.innerHTML = value;\n");
    writeBaseline("[\"" + relative + ":1\"]");

    assertThat(run(null).exitCode()).isZero();

    write(relative, "const prefix = true;\nknown.innerHTML = value;\n");
    var moved = run(null);
    assertThat(moved.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(moved.out()).contains("\"line\":2");

    write(BASELINE, "{not-json\n");
    assertThat(run(null).exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
  }

  @Test
  void everyInvalidCanonicalBaselineShapeExposesTheKnownFinding() throws Exception {
    var relative = STATIC_JS + "/known.js";
    var key = relative + ":1";
    write(relative, "known.innerHTML = value;\n");
    var valid =
        "{\"version\":1,\"rules\":{\"raw-innerhtml\":{\"entries\":[\""
            + key
            + "\"]},\"layout-inline-style\":{\"entries\":[]}}}";
    var invalidDocuments =
        List.of(
            valid + " {}",
            valid.replace("\"version\":1", "\"version\":2"),
            valid.replace("\"version\":1", "\"version\":4294967297"),
            "{\"version\":1,\"rules\":[]}",
            "{\"version\":1,\"rules\":{\"raw-innerhtml\":[]}}",
            "{\"version\":1,\"rules\":{\"raw-innerhtml\":{\"entries\":[1]}}}",
            valid.substring(0, valid.length() - 1) + ",\"extra\":true}");

    for (var invalid : invalidDocuments) {
      write(BASELINE, invalid);

      var result = run(null);

      assertThat(result.exitCode()).as(invalid).isEqualTo(QualityGateExitCodes.VIOLATIONS);
      assertThat(result.out()).as(invalid).contains(relative);
    }
  }

  @Test
  void replacementDecodingStillFindsAssignmentsAndSnippetIsLimitedTo120CodePoints()
      throws Exception {
    var prefix = "node.innerHTML = '";
    var longValue = "界".repeat(150);
    var suffix = "';";
    var text = prefix + longValue + suffix;
    var bytes = text.getBytes(StandardCharsets.UTF_8);
    var malformed = java.util.Arrays.copyOf(bytes, bytes.length + 1);
    malformed[malformed.length - 1] = (byte) 0xFF;
    var path = repo.resolve(STATIC_JS + "/malformed.js");
    Files.createDirectories(path.getParent());
    Files.write(path, malformed);

    var result = run(null);
    var expectedSnippet = prefix + "界".repeat(120 - prefix.codePointCount(0, prefix.length()));

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).contains("\"snippet\":\"" + expectedSnippet + "\"");
  }

  private Result run(String changedFiles) {
    var args =
        new String[] {
          "--repo-root", repo.toString(), "--paths", repo.toString(), "--rules", "raw-innerhtml"
        };
    var environment =
        changedFiles == null
            ? Map.<String, String>of()
            : Map.of("QUALITY_CHANGED_FILES", changedFiles);
    var out = new ByteArrayOutputStream();
    var err = new ByteArrayOutputStream();
    var exitCode =
        QualityGateCli.run(
            args,
            environment,
            new PrintStream(err, true, StandardCharsets.UTF_8),
            new PrintStream(out, true, StandardCharsets.UTF_8));
    return new Result(
        exitCode, out.toString(StandardCharsets.UTF_8), err.toString(StandardCharsets.UTF_8));
  }

  private void writeBaseline(String entries) throws Exception {
    write(
        BASELINE,
        """
        {
          "version": 1,
          "rules": {
            "raw-innerhtml": {"entries": %s},
            "layout-inline-style": {"entries": []}
          }
        }
        """
            .formatted(entries));
  }

  private Path write(String relativePath, String content) throws Exception {
    var path = repo.resolve(relativePath);
    Files.createDirectories(path.getParent());
    return Files.writeString(path, content, StandardCharsets.UTF_8);
  }

  private record Result(int exitCode, String out, String err) {}
}
