package com.feipi.session.browser.quality.gates.cli;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 聚合 CLI 的候选解析、JSON、exit code 与 API maintenance contract。 */
class QualityGateCliTest {

  @TempDir Path repo;

  @Test
  void aggregatesMultipleRulesInOneSummary() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Broken.java",
            """
            package example;
            /** @param value English only. */
            @SuppressWarnings("PMD.UnusedPrivateMethod")
            public record Broken(String value) {}
            """);

    var result = run("record-component-javadocs,no-pmd-suppressions", null, source);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"status\":\"FAILED\"")
        .contains("RECORD_COMPONENT_PARAM_NOT_CHINESE")
        .contains("PMD_SUPPRESSION_FORBIDDEN")
        .contains("\"rule\":\"record-component-javadocs\"")
        .contains("\"rule\":\"no-pmd-suppressions\"");
  }

  @Test
  void nonArtifactRuleIgnoresUnrelatedArtifactEnvironment() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Valid.java",
            """
            package example;
            /** @param value 中文说明。 */
            public record Valid(String value) {}
            """);
    var external = repo.resolveSibling(repo.getFileName() + "-outside").toAbsolutePath();

    var result =
        invoke(
            new String[] {
              "--repo-root",
              repo.toString(),
              "--paths",
              source.toString(),
              "--rules",
              "record-component-javadocs"
            },
            Map.of("FEIPI_QUALITY_ARTIFACT_DIR", external.toString()));

    assertThat(result.exitCode()).isZero();
    assertThat(result.out()).contains("\"status\":\"PASSED\"");
    assertThat(external).doesNotExist();
  }

  @Test
  void changedFilesSupportsEmptyAndWindowsPaths() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Broken.java",
            "package example; public record Broken(String value) {}\n");

    var empty = run("record-component-javadocs", "[]", source);
    var windows =
        run(
            "record-component-javadocs",
            "[\"java\\\\sample\\\\src\\\\main\\\\java\\\\example\\\\Broken.java\"]",
            source);

    assertThat(empty.exitCode()).isZero();
    assertThat(empty.out())
        .contains("\"status\":\"NOT_APPLICABLE\"")
        .contains("\"candidateCount\":0")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"NOT_APPLICABLE\",\"candidateCount\":0,\"violationCount\":0,\"advisoryCount\":0}");
    assertThat(windows.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(windows.out()).contains("java/sample/src/main/java/example/Broken.java");
  }

  @Test
  void invalidChangedFilesFailsClosed() throws Exception {
    var source = write("java/sample/src/main/java/example/Valid.java", "class Valid {}\n");

    var result = run("record-component-javadocs", "not-json", source);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(result.err()).contains("failed closed").contains("JSON string array");
  }

  @Test
  void mixedRulesApplyChangedFilesPerRule() throws Exception {
    write(
        "config/technical-terms.json",
        "{\"canonical_terms\":[\"Java\"],\"forbidden_translations\":[]}\n");
    write(
        "java/sample/src/main/java/example/Unmodified.java",
        """
        package example;
        // Read cached execution result from local storage.
        public record Unmodified(String value) {}
        """);
    write(
        "java/sample/src/main/java/example/Modified.java",
        "package example; public record Modified(String value) {}\n");
    var result =
        invoke(
            new String[] {
              "--repo-root",
              repo.toString(),
              "--paths",
              repo.resolve("java").toString(),
              "--rules",
              "java-comment-language,record-component-javadocs"
            },
            Map.of(
                "QUALITY_CHANGED_FILES", "[\"java/sample/src/main/java/example/Modified.java\"]"));

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains(
            "\"rule\":\"java-comment-language\",\"path\":\"java/sample/src/main/java/example/Unmodified.java\"")
        .contains(
            "\"rule\":\"record-component-javadocs\",\"path\":\"java/sample/src/main/java/example/Modified.java\"")
        .doesNotContain(
            "\"rule\":\"record-component-javadocs\",\"path\":\"java/sample/src/main/java/example/Unmodified.java\"");
  }

  @Test
  void templateRuleStaysRepositoryWideWhenAggregatedWithIncrementalJavaRule() throws Exception {
    write(
        "java/web/src/main/resources/templates/broken.html",
        "<button onclick=\"run()\">运行</button>\n");
    write(
        "java/sample/src/main/java/example/Valid.java",
        """
        package example;
        /** @param value 中文说明。 */
        public record Valid(String value) {}
        """);

    var result =
        invoke(
            new String[] {
              "--repo-root",
              repo.toString(),
              "--paths",
              repo.resolve("java").toString(),
              "--rules",
              "template-contract,record-component-javadocs"
            },
            Map.of("QUALITY_CHANGED_FILES", "[\"java/sample/src/main/java/example/Valid.java\"]"));

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains(
            "{\"rule\":\"template-contract\",\"status\":\"FAILED\",\"candidateCount\":2,\"violationCount\":1,\"advisoryCount\":0}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0,\"advisoryCount\":0}")
        .contains("ONCLICK_FORBIDDEN");
  }

  @Test
  void staticResourceRuleStaysRepositoryWideWhenAggregatedWithIncrementalJavaRule()
      throws Exception {
    write(
        "config/web-quality-baselines.json",
        "{\"version\":1,\"rules\":{\"static-resource-contract\":{"
            + "\"component_override_violations\":[],\"selector_depth_violations\":[]}}}\n");
    write(
        "java/web/src/main/resources/templates/base.html",
        """
        /static/css/tokens.css
        /static/css/base.css
        /static/css/shell.css
        /static/css/ui-primitives.css
        {% block head_extra %}
        """);
    write("java/web/src/main/resources/static/css/valid.css", ".valid { color: red; }\n");
    write("java/web/src/main/resources/static/js/broken.js", "eval(userInput);\n");
    write(
        "java/sample/src/main/java/example/Valid.java",
        """
        package example;
        /** @param value 中文说明。 */
        public record Valid(String value) {}
        """);

    var result =
        invoke(
            new String[] {
              "--repo-root",
              repo.toString(),
              "--paths",
              repo.resolve("java").toString(),
              "--rules",
              "static-resource-contract,record-component-javadocs"
            },
            Map.of("QUALITY_CHANGED_FILES", "[\"java/sample/src/main/java/example/Valid.java\"]"));

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains(
            "{\"rule\":\"static-resource-contract\",\"status\":\"FAILED\",\"candidateCount\":5,\"violationCount\":1,\"advisoryCount\":0}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0,\"advisoryCount\":0}")
        .contains("EVAL_FORBIDDEN");
  }

  @Test
  void rawAndLayoutRulesStayIndependentAndRepositoryWideWithIncrementalJavaRule() throws Exception {
    write(
        "config/web-quality-baselines.json",
        "{\"version\":1,\"rules\":{"
            + "\"raw-innerhtml\":{\"entries\":[]},"
            + "\"layout-inline-style\":{\"entries\":[]}}}\n");
    write("java/web/src/main/resources/static/js/raw.js", "node.innerHTML = value;\n");
    write(
        "java/web/src/main/resources/templates/layout.html",
        "<div style=\"display:grid\">布局</div>\n");
    write(
        "java/sample/src/main/java/example/Valid.java",
        """
        package example;
        /** @param value 中文说明。 */
        public record Valid(String value) {}
        """);

    var result =
        invoke(
            new String[] {
              "--repo-root",
              repo.toString(),
              "--paths",
              repo.toString(),
              "--rules",
              "raw-innerhtml,layout-inline-style,record-component-javadocs"
            },
            Map.of("QUALITY_CHANGED_FILES", "[\"java/sample/src/main/java/example/Valid.java\"]"));

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains(
            "{\"rule\":\"raw-innerhtml\",\"status\":\"FAILED\",\"candidateCount\":2,\"violationCount\":1,\"advisoryCount\":0}")
        .contains(
            "{\"rule\":\"layout-inline-style\",\"status\":\"FAILED\",\"candidateCount\":3,\"violationCount\":1,\"advisoryCount\":0}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0,\"advisoryCount\":0}")
        .contains("RAW_INNERHTML_NEW")
        .contains("LAYOUT_INLINE_STYLE_NEW");
  }

  @Test
  void testOnlyJavaDoesNotTurnZeroCandidateMainRuleIntoPassed() throws Exception {
    write(
        "config/technical-terms.json",
        "{\"canonical_terms\":[\"Java\"],\"forbidden_translations\":[]}\n");
    var source =
        write(
            "java/sample/src/test/java/example/SampleTest.java",
            "package example; // 验证测试路径。\nclass SampleTest {}\n");

    var result =
        run(
            "java-comment-language,record-component-javadocs",
            "[\"java/sample/src/test/java/example/SampleTest.java\"]",
            source);

    assertThat(result.exitCode()).isZero();
    assertThat(result.out())
        .contains("\"status\":\"PASSED\"")
        .contains(
            "{\"rule\":\"java-comment-language\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0,\"advisoryCount\":0}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"NOT_APPLICABLE\",\"candidateCount\":0,\"violationCount\":0,\"advisoryCount\":0}");
  }

  @Test
  void unknownRuleIsRejected() throws Exception {
    var source =
        write(
            "java/sample/src/main/kotlin/example/Sample.kt",
            "package example\n// 验证 Kotlin 路径。\nclass Sample\n");

    var result = run("missing-rule", null, source);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(result.err()).contains("Unknown rules: [missing-rule]");
  }

  @Test
  void preservesOnlyTheExactBackgroundScannerPmdException() throws Exception {
    var source =
        write(
            "java/scan-engine/src/main/java/com/feipi/session/browser/scan/engine/BackgroundScanner.java",
            """
            package com.feipi.session.browser.scan.engine;
            @SuppressWarnings({"PMD.CloseResource", "PMD.Other"})
            public class BackgroundScanner {}
            """);

    var result = run("no-pmd-suppressions", null, source);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).doesNotContain("PMD.CloseResource").contains("PMD.Other");
  }

  private Result run(String rules, String changedFiles, Path source) {
    var args =
        new String[] {
          "--repo-root", repo.toString(), "--paths", source.toString(), "--rules", rules
        };
    var environment =
        changedFiles == null
            ? Map.<String, String>of()
            : Map.of("QUALITY_CHANGED_FILES", changedFiles);
    return invoke(args, environment);
  }

  private Result invoke(String[] args, Map<String, String> environment) {
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

  private Path write(String relativePath, String content) throws Exception {
    var path = repo.resolve(relativePath);
    Files.createDirectories(path.getParent());
    return Files.writeString(path, content, StandardCharsets.UTF_8);
  }

  private record Result(int exitCode, String out, String err) {}
}
