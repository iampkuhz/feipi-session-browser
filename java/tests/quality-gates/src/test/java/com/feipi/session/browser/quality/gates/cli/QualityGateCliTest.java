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
            "{\"rule\":\"record-component-javadocs\",\"status\":\"NOT_APPLICABLE\",\"candidateCount\":0,\"violationCount\":0}");
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
            "{\"rule\":\"template-contract\",\"status\":\"FAILED\",\"candidateCount\":2,\"violationCount\":1}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0}")
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
            "{\"rule\":\"static-resource-contract\",\"status\":\"FAILED\",\"candidateCount\":5,\"violationCount\":1}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0}")
        .contains("EVAL_FORBIDDEN");
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
            "{\"rule\":\"java-comment-language\",\"status\":\"PASSED\",\"candidateCount\":1,\"violationCount\":0}")
        .contains(
            "{\"rule\":\"record-component-javadocs\",\"status\":\"NOT_APPLICABLE\",\"candidateCount\":0,\"violationCount\":0}");
  }

  @Test
  void zeroCandidateRuleIsNotExecuted() throws Exception {
    write(
        "config/technical-terms.json",
        "{\"canonical_terms\":[\"Java\"],\"forbidden_translations\":[]}\n");
    var source =
        write(
            "java/sample/src/main/kotlin/example/Sample.kt",
            "package example\n// 验证 Kotlin 路径。\nclass Sample\n");

    var result = run("java-comment-language,java-api-snapshot", null, source);

    assertThat(result.exitCode()).isZero();
    assertThat(result.out())
        .doesNotContain("JAVA_API_SNAPSHOT_MISSING")
        .contains(
            "{\"rule\":\"java-api-snapshot\",\"status\":\"NOT_APPLICABLE\",\"candidateCount\":0,\"violationCount\":0}");
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

  @Test
  void writesAndChecksApiSnapshotOnlyInExplicitMode() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Sample.java",
            """
            package example;
            /** @param value 中文说明。 */
            public record Sample(String value) {}
            """);
    var snapshot = repo.resolve("config/api-snapshots/java-public-api.txt");
    var write = runApi(source, snapshot, true);
    var check = runApi(source, snapshot, false);

    assertThat(write.exitCode()).isZero();
    assertThat(check.exitCode()).isZero();
    assertThat(Files.readString(snapshot))
        .contains("Generated by runJavaQualityGates --write-api-snapshot")
        .contains("component example.Sample value: String")
        .contains("type example.Sample public record [sample] record Sample(String value)");
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

  private Result runApi(Path source, Path snapshot, boolean write) {
    var args = new java.util.ArrayList<String>();
    java.util.Collections.addAll(
        args,
        "--repo-root",
        repo.toString(),
        "--paths",
        source.toString(),
        "--rules",
        "java-api-snapshot",
        "--api-snapshot",
        snapshot.toString());
    if (write) {
      args.add("--write-api-snapshot");
    }
    return invoke(args.toArray(String[]::new), Map.of());
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
