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

/** layout-inline-style 的 HTML/JS 边界、扫描范围、baseline 与诊断长度 corpus。 */
class LayoutInlineStyleRuleTest {

  private static final String BASELINE =
      "java/tests/quality-gates/config/web-quality-baselines.json";
  private static final String TEMPLATES = "java/web/src/main/resources/templates";
  private static final String STATIC_JS = "java/web/src/main/resources/static/js";

  @TempDir Path repo;

  @BeforeEach
  void createEmptyBaseline() throws Exception {
    writeBaseline("[]");
  }

  @Test
  void htmlScannerKeepsQuoteCaseCommentTemplateAndCustomPropertyBoundaries() throws Exception {
    write(
        TEMPLATES + "/boundaries.html",
        """
        <div style="color:red">clean</div>
        <div style="display:flex">double</div>
        <div STYLE='POSITION:absolute'>single</div>
        <div style="{{ grid_style }}">template</div>
        <div style="--segment-width:200px">custom</div>
        <div style="--segment-width:200px; margin-left:1px">mixed</div>
        {# <div style="display:grid">comment</div> #}
        <!-- <div style="display:grid">comment</div> -->
        text <!-- <div style="display:grid">inline comment stays visible</div> -->
        """);

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.err()).isEmpty();
    assertThat(result.out())
        .contains("\"violationCount\":4")
        .contains("LAYOUT_INLINE_STYLE_NEW")
        .contains("\"source\":\"html\"")
        .contains("\"line\":2")
        .contains("\"line\":3")
        .contains("\"line\":6")
        .contains("\"line\":9")
        .contains("请移除 inline style 并改用 CSS class 或 CSS custom property");
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
        TEMPLATES + "/unicode-lines.html",
        nonBreakingSpace
            + "<!-- <div style=\"display:grid\">ignored</div> -->"
            + lineSeparator
            + "<div style"
            + nonBreakingSpace
            + "="
            + nonBreakingSpace
            + "\"display"
            + nonBreakingSpace
            + ":grid\">first</div>"
            + nextLine
            + "<div style='position:absolute'>second</div>"
            + verticalTab
            + "<div style=\"{{ grid_style }}\">ignored template</div>");
    write(
        STATIC_JS + "/unicode-lines.js",
        nonBreakingSpace
            + "// node.style.display = value;"
            + paragraphSeparator
            + "node.style.width"
            + nonBreakingSpace
            + "= value;"
            + formFeed
            + "node.style.height = value;");

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"violationCount\":4")
        .contains("\"source\":\"html\"")
        .contains("\"source\":\"js\"")
        .doesNotContain("ignored template")
        .doesNotContain("node.style.display");
  }

  @Test
  void reportsHtmlBeforeJavaScriptWithStablePathOrder() throws Exception {
    write(TEMPLATES + "/z.html", "<div style=\"display:grid\">z</div>\n");
    write(TEMPLATES + "/a.html", "<div style=\"display:grid\">a</div>\n");
    write(STATIC_JS + "/z.js", "node.style.width = value;\n");
    write(STATIC_JS + "/a.js", "node.style.width = value;\n");

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .containsSubsequence(
            "templates/a.html", "templates/z.html", "static/js/a.js", "static/js/z.js");
  }

  @Test
  void javascriptScannerKeepsTheExactLayoutPropertyAndCamelCaseSet() throws Exception {
    var properties =
        List.of(
            "display",
            "position",
            "flex",
            "grid",
            "width",
            "height",
            "minWidth",
            "minHeight",
            "maxWidth",
            "maxHeight",
            "top",
            "left",
            "right",
            "bottom",
            "padding",
            "paddingTop",
            "paddingRight",
            "paddingBottom",
            "paddingLeft",
            "margin",
            "marginTop",
            "marginRight",
            "marginBottom",
            "marginLeft",
            "overflow",
            "overflowX",
            "overflowY",
            "zIndex");
    var text = new StringBuilder("node.style.color = 'red';\n");
    for (var property : properties) {
      text.append("node.style.").append(property).append(" = value;\n");
    }
    text.append("// node.style.display = value;\n");
    text.append("/* node.style.position = value; */\n");
    text.append(" * node.style.width = value;\n");
    write(STATIC_JS + "/properties.js", text.toString());

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"violationCount\":" + properties.size())
        .contains("\"source\":\"js\"");
  }

  @Test
  void scansOnlyTemplatesAndStaticJsWithoutChangedFileNarrowing() throws Exception {
    write(TEMPLATES + "/generated/page.html", "<div style=\"display:grid\">page</div>\n");
    write(STATIC_JS + "/tmp/page.js", "node.style.width = value;\n");
    write("tests/browser.js", "test.style.width = value;\n");
    write("scripts/tool.js", "tool.style.width = value;\n");

    var result = run("[\"tests/browser.js\"]");

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"violationCount\":2")
        .contains("generated/page.html")
        .contains("static/js/tmp/page.js")
        .doesNotContain("tests/browser.js")
        .doesNotContain("scripts/tool.js");
  }

  @Test
  void baselineUsesOnlyExactFileLineAndSnippetIsLimitedTo140CodePoints() throws Exception {
    var relative = TEMPLATES + "/known.html";
    var prefix = "<div style=\"display:grid\">";
    var line = prefix + "界".repeat(160) + "</div>";
    write(relative, line + "\n");
    writeBaseline("[\"" + relative + ":1\"]");

    assertThat(run(null).exitCode()).isZero();

    writeBaseline("[]");
    var result = run(null);
    var expectedSnippet = prefix + "界".repeat(140 - prefix.codePointCount(0, prefix.length()));
    var escapedSnippet = expectedSnippet.replace("\\", "\\\\").replace("\"", "\\\"");
    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).contains("\"snippet\":\"" + escapedSnippet + "\"");

    write(BASELINE, "{not-json\n");
    assertThat(run(null).exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
  }

  @Test
  void everyInvalidCanonicalBaselineShapeExposesTheKnownFinding() throws Exception {
    var relative = TEMPLATES + "/known.html";
    var key = relative + ":1";
    write(relative, "<div style=\"display:grid\">known</div>\n");
    var valid =
        "{\"version\":1,\"rules\":{\"raw-innerhtml\":{\"entries\":[]},"
            + "\"layout-inline-style\":{\"entries\":[\""
            + key
            + "\"]}}}";
    var invalidDocuments =
        List.of(
            valid + " {}",
            valid.replace("\"version\":1", "\"version\":2"),
            valid.replace("\"version\":1", "\"version\":4294967297"),
            "{\"version\":1,\"rules\":[]}",
            "{\"version\":1,\"rules\":{\"layout-inline-style\":[]}}",
            "{\"version\":1,\"rules\":{\"layout-inline-style\":{\"entries\":[1]}}}",
            valid.substring(0, valid.length() - 1) + ",\"extra\":true}");

    for (var invalid : invalidDocuments) {
      write(BASELINE, invalid);

      var result = run(null);

      assertThat(result.exitCode()).as(invalid).isEqualTo(QualityGateExitCodes.VIOLATIONS);
      assertThat(result.out()).as(invalid).contains(relative);
    }
  }

  private Result run(String changedFiles) {
    var args =
        new String[] {
          "--repo-root",
          repo.toString(),
          "--paths",
          repo.toString(),
          "--rules",
          "layout-inline-style"
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
            "raw-innerhtml": {"entries": []},
            "layout-inline-style": {"entries": %s}
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
