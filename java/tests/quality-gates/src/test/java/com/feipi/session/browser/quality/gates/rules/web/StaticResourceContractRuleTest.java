package com.feipi.session.browser.quality.gates.rules.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.quality.gates.cli.QualityGateCli;
import com.feipi.session.browser.quality.gates.cli.QualityGateExitCodes;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** HOOK-HARNESS-013：静态资源规则的有效、违规、基线与边界样本。 */
class StaticResourceContractRuleTest {

  private static final String STATIC = "java/web/src/main/resources/static";
  private static final String TEMPLATES = "java/web/src/main/resources/templates";
  private static final String BASELINE = "config/web-quality-baselines.json";

  @TempDir Path repo;

  @BeforeEach
  void createValidRepository() throws Exception {
    write(STATIC + "/css/valid.css", ".valid { color: red; }\n");
    write(STATIC + "/js/valid.js", "const valid = true;\n");
    write(TEMPLATES + "/base.html", validBaseTemplate());
    writeBaseline("[]", "[]");
  }

  @Test
  void validResourcesStayWithinStaticResourceRuleOwnership() throws Exception {
    write(STATIC + "/js/raw.js", "node.innerHTML = userInput;\nnode.style.display = 'none';\n");
    write(TEMPLATES + "/page.html", "<div style=\"display:grid\">页面</div>\n");
    write(STATIC + "/css/shell-duplicate.css", ".app-shell { display: grid; }\n");
    write(STATIC + "/css/tokens.css", ".not-root { color: red; }\n");
    write(STATIC + "/css/fixed.css", ".floating { position: fixed; }\n");

    var result = run(null);

    assertThat(result.exitCode()).isZero();
    assertThat(result.out())
        .contains("\"status\":\"PASSED\"")
        .doesNotContain("INNERHTML")
        .doesNotContain("INLINE_STYLE")
        .doesNotContain("SHELL_OWNER")
        .doesNotContain("CSS_OWNERSHIP")
        .doesNotContain("POSITION_FIXED");
  }

  @Test
  void reportsOwnedBlockingRules() throws Exception {
    write(
        STATIC + "/css/bad.css", "/* color: red !important; */\n.payload-modal { color: red; }\n");
    write(STATIC + "/css/dead.css", "");
    write(STATIC + "/js/eval.js", "const text = 'eval(';\n");
    write(
        TEMPLATES + "/page.html",
        "<link href=\"/static/css/tokens.css?version=1\" rel=\"stylesheet\">\n");

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("IMPORTANT_FORBIDDEN")
        .contains("DEAD_CSS_EMPTY")
        .contains("DUPLICATE_BASE_CSS")
        .contains("PAYLOAD_MODAL_OWNER")
        .contains("EVAL_FORBIDDEN")
        .contains("COMPONENT_OVERRIDE_NEW");
  }

  @Test
  void cssLoadOrderUsesFirstLiteralPositionsAndStopsAtFirstMissingItem() throws Exception {
    write(TEMPLATES + "/base.html", "/static/css/tokens.css\n{% block head_extra %}\n");

    var missing = run(null);

    assertThat(missing.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(missing.out())
        .contains("CSS_LOAD_ITEM_MISSING")
        .contains("/static/css/base.css")
        .doesNotContain("CSS_LOAD_ORDER_INVALID");

    write(
        TEMPLATES + "/base.html",
        """
        /static/css/tokens.css
        /static/css/base.css
        /static/css/ui-primitives.css
        /static/css/shell.css
        {% block head_extra %}
        """);

    var inverted = run(null);

    assertThat(inverted.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(inverted.out()).contains("CSS_LOAD_ORDER_INVALID");
  }

  @Test
  void deadCssPreservesImportJunkAndSingleBraceBoundaries() throws Exception {
    write(STATIC + "/css/import.css", "@import url('base.css');\nnot-css\n");
    write(STATIC + "/css/single-brace.css", "{\n");

    assertThat(run(null).exitCode()).isZero();

    write(STATIC + "/css/comment-only.css", "/* comment */\n");
    write(STATIC + "/css/no-body.css", "color: red\n");

    var invalid = run(null);

    assertThat(invalid.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(invalid.out()).contains("DEAD_CSS_EMPTY").contains("DEAD_CSS_NO_RULE_BODY");
  }

  @Test
  void viewportPolicyAllowsDesktopWidthsAndRejectsNonDesktopPatterns() throws Exception {
    write(
        STATIC + "/css/desktop.css",
        """
        /* @media tablet and (max-width: 768px) */
        @media (min-width: 1512px) { .desktop { display: grid; } }
        """);
    write(
        STATIC + "/js/viewport-notes.js",
        "// @media tablet breakpoint\nconst desktopViewport = '1440px';\n");

    assertThat(run(null).exitCode()).isZero();

    write(
        STATIC + "/css/mobile.css",
        """
        @media (max-width: 768px) { .compact { display: block; } }
        @media screen and (min-width: 768px) and (max-width: 1024px) {
          .tablet { display: block; }
        }
        """);

    var invalid = run(null);

    assertThat(invalid.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(invalid.out())
        .contains("VIEWPORT_OUTSIDE_DESKTOP_CONTRACT")
        .contains("mobile.css")
        .contains("desktop-viewports-only");
  }

  @Test
  void emptyJavaScriptIsReportedAfterRemovingLineAndBlockComments() throws Exception {
    write(
        STATIC + "/js/comment-only.js",
        """
        // comment-only fixture
        /* no executable statements remain */
        """);

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("DEAD_JS_EMPTY")
        .contains("comment-only.js")
        .contains("non-empty-static-resource");
  }

  @Test
  void duplicateCssRequiresLowercaseDoubleQuotedHrefAndSkipsBaseFileNames() throws Exception {
    write(
        TEMPLATES + "/boundary.html",
        """
        <link href='/static/css/tokens.css'>
        <link HREF="/static/css/base.css">
        <link href="/static/css/SHELL.CSS">
        """);
    write(TEMPLATES + "/nested/base.html", "<link href=\"/static/css/ui-primitives.css\">\n");

    assertThat(run(null).exitCode()).isZero();

    write(TEMPLATES + "/boundary.html", "<!-- href=\"/static/css/base.css\" 重复加载 -->\n");

    var invalid = run(null);

    assertThat(invalid.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(invalid.out()).contains("DUPLICATE_BASE_CSS").contains("base.css");
  }

  @Test
  void payloadModalKeepsCurrentPrefixesBemAndCommentBoundaries() throws Exception {
    write(
        STATIC + "/css/payload-boundary.css",
        """
        .session-detail-page .payload-modal { color: red; }
        .sd-page .payload-modal { color: red; }
        body .payload-modal { color: red; }
        .payload-modal--wide { color: red; }
        """);
    write(STATIC + "/css/ui-primitives/owned.css", ".payload-modal { color: red; }\n");

    assertThat(run(null).exitCode()).isZero();

    write(
        STATIC + "/css/payload-bad.css",
        """
        .payload-modal-wide { color: red; }
        #payload-modal { color: red; }
        /*
        .payload-modal { color: red; }
        */
        """);

    var invalid = run(null);

    assertThat(invalid.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(invalid.out()).contains("PAYLOAD_MODAL_OWNER").contains("\"count\":\"3\"");
  }

  @Test
  void componentBaselineKeepsBroadSubstringSuppressionWithoutWarnings() throws Exception {
    write(STATIC + "/css/known.css", ".btn, .toast { color: red; }\n");
    writeBaseline("[\"baseline.css:.btn\"]", "[]");

    var known = run(null);

    assertThat(known.exitCode()).isZero();
    assertThat(known.out()).doesNotContain("WARN").doesNotContain("COMPONENT_OVERRIDE_NEW");

    write(STATIC + "/css/unknown.css", ".modal { color: red; }\n");

    var unknown = run(null);

    assertThat(unknown.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(unknown.out()).contains("COMPONENT_OVERRIDE_NEW").contains(".modal");
  }

  @Test
  void selectorDepthKeepsParserBoundaryAndBroadSuppression() throws Exception {
    write(
        STATIC + "/css/known-depth.css",
        """
        .known .a .b .c { color: red; }
        .also-unknown .a .b .c { color: blue; }
        .a .b .c { color: green; }
        .a:not(.x .y) .b .c { color: black; }
        """);
    writeBaseline("[]", "[\"baseline.css:.known .a .b .c\"]");

    assertThat(run(null).exitCode()).isZero();

    write(STATIC + "/css/unknown-depth.css", ".u > .a + .b .c { color: red; }\n");

    var invalid = run(null);

    assertThat(invalid.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(invalid.out()).contains("SELECTOR_DEPTH_NEW").contains("depth=4");
  }

  @Test
  void missingStaticOrBaseFailsInsteadOfBecomingNotApplicable() throws Exception {
    deleteTree(repo.resolve(STATIC));

    var missingStatic = run(null);

    assertThat(missingStatic.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(missingStatic.out())
        .contains("STATIC_DIRECTORY_MISSING")
        .contains("\"status\":\"FAILED\"")
        .doesNotContain("NOT_APPLICABLE")
        .doesNotContain("BASE_TEMPLATE_MISSING");

    write(STATIC + "/css/valid.css", ".valid { color: red; }\n");
    write(STATIC + "/js/valid.js", "const valid = true;\n");
    deleteTree(repo.resolve(TEMPLATES));

    var missingBase = run(null);

    assertThat(missingBase.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(missingBase.out())
        .contains("BASE_TEMPLATE_MISSING")
        .doesNotContain("NOT_APPLICABLE")
        .doesNotContain("DUPLICATE_BASE_CSS");
  }

  @Test
  void malformedUtf8AndExcludedDirectoryNamesRemainInTheWebCorpus() throws Exception {
    var css = repo.resolve(STATIC + "/generated/broken.css");
    Files.createDirectories(css.getParent());
    Files.write(
        css,
        new byte[] {
          (byte) 0xC3,
          '.',
          'o',
          'k',
          ' ',
          '{',
          ' ',
          '!',
          'i',
          'm',
          'p',
          'o',
          'r',
          't',
          'a',
          'n',
          't',
          ';',
          ' ',
          '}'
        });
    write(STATIC + "/tmp/eval.js", "// eval(userInput)\n");

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.err()).isEmpty();
    assertThat(result.out()).contains("IMPORTANT_FORBIDDEN").contains("EVAL_FORBIDDEN");
  }

  @Test
  void malformedUtf8BaseTemplateFailsClosedEvenWhenAllRequiredLiteralsRemain() throws Exception {
    var validBytes = validBaseTemplate().getBytes(StandardCharsets.UTF_8);
    var malformedBytes = java.util.Arrays.copyOf(validBytes, validBytes.length + 1);
    malformedBytes[malformedBytes.length - 1] = (byte) 0xFF;
    Files.write(repo.resolve(TEMPLATES + "/base.html"), malformedBytes);

    var result = run(null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.err()).isEmpty();
    assertThat(result.out()).contains("BASE_TEMPLATE_UTF8_INVALID");
  }

  @Test
  void changedFilesDoNotShrinkTheStaticResourceCorpus() throws Exception {
    write(STATIC + "/js/unmodified-broken.js", "eval(userInput);\n");

    var result = run("[\"java/web/src/main/resources/static/css/valid.css\"]");

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).contains("unmodified-broken.js").contains("EVAL_FORBIDDEN");
  }

  @Test
  void missingOrMalformedBaselineBehavesAsAnEmptyFailClosedBaseline() throws Exception {
    write(STATIC + "/css/known.css", ".btn { color: red; }\n");
    Files.delete(repo.resolve(BASELINE));

    var missing = run(null);

    assertThat(missing.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(missing.out()).contains("COMPONENT_OVERRIDE_NEW");

    write(BASELINE, "{not-json\n");

    var malformed = run(null);

    assertThat(malformed.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(malformed.out()).contains("COMPONENT_OVERRIDE_NEW");
  }

  private Result run(String changedFiles) {
    var out = new ByteArrayOutputStream();
    var err = new ByteArrayOutputStream();
    var args =
        new String[] {
          "--repo-root",
          repo.toString(),
          "--paths",
          repo.resolve(STATIC) + "," + repo.resolve(TEMPLATES),
          "--rules",
          "static-resource-contract"
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

  private void writeBaseline(String componentEntries, String selectorEntries) throws Exception {
    write(
        BASELINE,
        """
        {
          "version": 1,
          "rules": {
            "static-resource-contract": {
              "component_override_violations": %s,
              "selector_depth_violations": %s
            }
          }
        }
        """
            .formatted(componentEntries, selectorEntries));
  }

  private Path write(String relativePath, String text) throws Exception {
    var path = repo.resolve(relativePath);
    Files.createDirectories(path.getParent());
    return Files.writeString(path, text, StandardCharsets.UTF_8);
  }

  private static String validBaseTemplate() {
    return """
        <link href="/static/css/tokens.css">
        <link href="/static/css/base.css">
        <link href="/static/css/shell.css">
        <link href="/static/css/ui-primitives.css">
        {% block head_extra %}{% endblock %}
        """;
  }

  private static void deleteTree(Path root) throws Exception {
    if (!Files.exists(root)) {
      return;
    }
    try (var paths = Files.walk(root)) {
      for (var path : paths.sorted(Comparator.reverseOrder()).toList()) {
        Files.delete(path);
      }
    }
  }

  private record Result(int exitCode, String out, String err) {}
}
