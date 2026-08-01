package com.feipi.session.browser.quality.gates.rules;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.quality.gates.cli.QualityGateCli;
import com.feipi.session.browser.quality.gates.cli.QualityGateExitCodes;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Java 注释语言规则的词法、阈值、策略与增量 corpus。 */
class JavaCommentLanguageRuleTest {

  @TempDir Path repo;

  @BeforeEach
  void writePolicy() throws Exception {
    write(
        "config/technical-terms.json",
        """
        {
          "canonical_terms": ["Java", "JSON", "source", "error"],
          "forbidden_translations": ["爪哇"]
        }
        """);
  }

  @Test
  void acceptsChineseThresholdsAndCanonicalTerms() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Sample.java",
            """
            class Sample {
              // 退出码：mismatch → 1，source error → 2
              /* 负责读取 JSON result 并返回结果。 */
              /** 此对象表示 Java 来源信息。 */
            }
            """);

    var result = run(source, null);

    assertThat(result.exitCode()).isZero();
    assertThat(result.out()).contains("\"status\":\"PASSED\"");
  }

  @Test
  void ignoresMarkersInsideStringsCharactersAndTextBlocks() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Literals.java",
            String.join(
                    "\n",
                    "class Literals {",
                    "  String line = \"// Read cached execution result\";",
                    "  char slash = '/';",
                    "  String block = " + "\"\"\"",
                    "      /* Read cached execution result */",
                    "      // English text",
                    "      " + "\"\"\";",
                    "}")
                + "\n");

    assertThat(run(source, null).exitCode()).isZero();
  }

  @Test
  void reportsEnglishForbiddenLowInformationAndInheritDoc() throws Exception {
    var source =
        write(
            "java/sample/src/main/java/example/Broken.java",
            """
            class Broken {
              // Read cached execution result from local storage.
              // TODO 待补充
              // 使用爪哇实现边界检查。
              /** {@inheritDoc} */
            }
            """);

    var result = run(source, null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("COMMENT_NOT_CHINESE_DOMINANT")
        .contains("COMMENT_LOW_INFORMATION")
        .contains("TECH_TERM_NOT_CANONICAL")
        .contains("INHERITDOC_WITHOUT_CHINESE")
        .contains("\"line\":2")
        .contains("\"line\":3")
        .contains("\"line\":4")
        .contains("\"line\":5");
  }

  @Test
  void supportsKotlinNestedBlocksAndGradleKotlinScripts() throws Exception {
    write(
        "java/sample/src/main/kotlin/example/Sample.kt",
        """
        class Sample {
          /* 中文 /* Read cached execution result from local storage. */ */
        }
        """);
    write(
        "gradle/build-logic/src/main/kotlin/sample.gradle.kts",
        """
        // Read cached execution result from local storage.
        plugins {}
        """);

    var result = run(repo, null);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("java/sample/src/main/kotlin/example/Sample.kt")
        .contains("gradle/build-logic/src/main/kotlin/sample.gradle.kts")
        .contains("COMMENT_NOT_CHINESE_DOMINANT");
  }

  @Test
  void changedFilesDoNotShrinkTheRepositoryWideCommentCorpus() throws Exception {
    write("java/sample/src/main/java/example/Valid.java", "class Valid { // 中文边界\n}\n");
    write(
        "java/sample/src/main/java/example/Broken.java",
        "class Broken { // Read cached execution result.\n}\n");

    var result = run(repo.resolve("java"), "[\"java/sample/src/main/java/example/Valid.java\"]");

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).contains("Broken.java").contains("\"candidateCount\":2");
  }

  @Test
  void missingOrInvalidPolicyFailsClosed() throws Exception {
    var source =
        write("java/sample/src/main/java/example/Sample.java", "class Sample { // 中文边界\n}\n");
    Files.delete(repo.resolve("config/technical-terms.json"));
    var missing = run(source, null);
    write("config/technical-terms.json", "{\"canonical_terms\": \"Java\"}\n");
    var invalid = run(source, null);

    assertThat(missing.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(missing.err()).contains("failed closed").contains("technical-terms.json");
    assertThat(invalid.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(invalid.err()).contains("failed closed").contains("canonical_terms");
  }

  private Result run(Path input, String changedFiles) {
    var args =
        new String[] {
          "--repo-root",
          repo.toString(),
          "--paths",
          input.toString(),
          "--rules",
          "java-comment-language"
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

  private Path write(String relativePath, String content) throws Exception {
    var path = repo.resolve(relativePath);
    Files.createDirectories(path.getParent());
    return Files.writeString(path, content, StandardCharsets.UTF_8);
  }

  private record Result(int exitCode, String out, String err) {}
}
