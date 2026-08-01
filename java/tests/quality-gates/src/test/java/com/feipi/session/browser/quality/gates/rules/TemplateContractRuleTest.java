package com.feipi.session.browser.quality.gates.rules;

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
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Jinja 模板基础契约的有效、违规、边界与必需目录 corpus。 */
class TemplateContractRuleTest {

  private static final String TEMPLATES = "java/web/src/main/resources/templates";

  @TempDir Path repo;

  @Test
  void acceptsClosedMarkersAndNonExactOnclickVariants() throws Exception {
    write(
        "valid.html",
        """
        {% if ready %}<button onClick="run()">{{ label }}</button>{% endif %}
        <button onclick ="run()">空白边界</button>
        <button ONCLICK="run()">大小写边界</button>
        %} }}
        """);

    var result = run(null);

    assertThat(result.exitCode()).isZero();
    assertThat(result.out()).contains("\"status\":\"PASSED\"").contains("\"candidateCount\":2");
  }

  @Test
  void reportsEachLegacyViolationInStableFileOrder() throws Exception {
    write("b.html", "<p>{{ value</p>\n");
    write("a.html", "{% if ready\n<button onclick=\"run()\">运行</button>\n");

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("JINJA_BLOCK_UNCLOSED")
        .contains("JINJA_EXPRESSION_UNCLOSED")
        .contains("ONCLICK_FORBIDDEN")
        .contains("\"line\":1")
        .contains("\"line\":2");
    assertThat(result.out().indexOf("a.html")).isLessThan(result.out().indexOf("b.html"));
  }

  @Test
  void missingTemplateDirectoryFailsInsteadOfBecomingNotApplicable() {
    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("TEMPLATE_DIRECTORY_MISSING")
        .contains("\"status\":\"FAILED\"")
        .contains("\"candidateCount\":1")
        .doesNotContain("NOT_APPLICABLE");
  }

  @Test
  void emptyOrHtmlFreeTemplateDirectoryFails() throws Exception {
    Files.createDirectories(repo.resolve(TEMPLATES));
    var empty = run(null);
    Files.writeString(repo.resolve(TEMPLATES).resolve("readme.txt"), "说明", StandardCharsets.UTF_8);
    var htmlFree = run(null);

    assertThat(empty.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(htmlFree.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(empty.out()).contains("TEMPLATE_HTML_MISSING");
    assertThat(htmlFree.out()).contains("TEMPLATE_HTML_MISSING");
  }

  @Test
  void malformedUtf8UsesReplacementAndStillChecksContract() throws Exception {
    var path = templatePath("broken.html");
    Files.write(path, new byte[] {'<', (byte) 0xC3, '>', 'o', 'n', 'c', 'l', 'i', 'c', 'k', '='});

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.err()).isEmpty();
    assertThat(result.out()).contains("ONCLICK_FORBIDDEN");
  }

  @Test
  void changedFilesDoNotShrinkTheTemplateCorpus() throws Exception {
    write("valid.html", "<p>有效模板</p>\n");
    write("broken.html", "<button onclick=\"run()\">运行</button>\n");

    var result = run("[\"java/web/src/main/resources/templates/valid.html\"]");

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).contains("broken.html").contains("\"candidateCount\":3");
  }

  @Test
  void scansHtmlBelowNamesExcludedOnlyForJvmSources() throws Exception {
    write("valid.html", "<p>有效模板</p>\n");
    for (var directory : List.of("generated", "gen", "vendor", "tmp")) {
      var broken = repo.resolve(TEMPLATES).resolve(directory).resolve("broken.html");
      Files.createDirectories(broken.getParent());
      Files.writeString(broken, "<button onclick=\"run()\">运行</button>\n", StandardCharsets.UTF_8);
    }

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("generated/broken.html")
        .contains("gen/broken.html")
        .contains("vendor/broken.html")
        .contains("tmp/broken.html")
        .contains("ONCLICK_FORBIDDEN")
        .contains("\"candidateCount\":6");
  }

  private Result run(String changedFiles) {
    var out = new ByteArrayOutputStream();
    var err = new ByteArrayOutputStream();
    var args =
        new String[] {
          "--repo-root",
          repo.toString(),
          "--paths",
          repo.resolve(TEMPLATES).toString(),
          "--rules",
          "template-contract"
        };
    var environment =
        changedFiles == null
            ? Map.<String, String>of()
            : Map.of("QUALITY_CHANGED_FILES", changedFiles);
    var exitCode =
        QualityGateCli.run(
            args,
            environment,
            new PrintStream(err, true, StandardCharsets.UTF_8),
            new PrintStream(out, true, StandardCharsets.UTF_8));
    return new Result(
        exitCode, out.toString(StandardCharsets.UTF_8), err.toString(StandardCharsets.UTF_8));
  }

  private Path write(String name, String text) throws Exception {
    return Files.writeString(templatePath(name), text, StandardCharsets.UTF_8);
  }

  private Path templatePath(String name) throws Exception {
    var templates = repo.resolve(TEMPLATES);
    Files.createDirectories(templates);
    return templates.resolve(name);
  }

  private record Result(int exitCode, String out, String err) {}
}
