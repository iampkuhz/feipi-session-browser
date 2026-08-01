package com.feipi.session.browser.quality.gates.rules.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.quality.gates.cli.QualityGateCli;
import com.feipi.session.browser.quality.gates.cli.QualityGateExitCodes;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** CSS ownership 旧 owner 的 parser、严重级别、artifact 与隔离路径 parity corpus。 */
class CssOwnershipRuleTest {

  private static final String CSS_ROOT = "java/web/src/main/resources/static/css";

  @TempDir Path repo;

  @Test
  void missingDirectoryBlocksAndWritesNullableLineArtifact() throws Exception {
    var artifacts = artifactRoot("missing");

    var result = run(artifacts);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out()).contains("\"status\":\"FAILED\"").contains("CSS_DIRECTORY_MISSING");
    assertThat(readJson(artifacts))
        .isEqualTo(
            """
            {
              "schemaVersion": 1,
              "gate": "css-ownership",
              "status": "FAIL",
              "filesScanned": 0,
              "selectorsAnalyzed": 0,
              "blockCount": 1,
              "warningCount": 0,
              "blocks": [
                {
                  "rule": "missing-dir",
                  "file": "N/A",
                  "line": null,
                  "detail": "CSS 目录不存在:%s"
                }
              ],
              "warnings": []
            }
            """
                .formatted(repo.resolve(CSS_ROOT)));
  }

  @Test
  void emptyDirectoryPassesWithByteExactArtifacts() throws Exception {
    Files.createDirectories(cssRoot());
    var artifacts = artifactRoot("empty");

    var result = run(artifacts);

    assertThat(result.exitCode()).isZero();
    assertThat(readText(artifacts))
        .isEqualTo(
            """
            ============================================================
            CSS Ownership Gate Report
            ============================================================
            Files scanned:      0
            Selectors analyzed: 0
            Block violations:   0
            Warnings:           0

            CSS ownership: PASS (no violations)
            ============================================================
            """);
    assertThat(readJson(artifacts))
        .isEqualTo(
            """
            {
              "schemaVersion": 1,
              "gate": "css-ownership",
              "status": "PASS",
              "filesScanned": 0,
              "selectorsAnalyzed": 0,
              "blockCount": 0,
              "warningCount": 0,
              "blocks": [],
              "warnings": []
            }
            """);
  }

  @Test
  void advisoryOnlyPassesWithoutWarningVocabularyInCliSummary() throws Exception {
    writeCss(
        "page.css",
        """
        .btn, :is(.card, .pill) { color: #123456; border-color: #fff; }
        .btn:hover { color: #abcdef; }
        """);
    var artifacts = artifactRoot("advisory");

    var result = run(artifacts);

    assertThat(result.exitCode()).isZero();
    assertThat(result.out())
        .contains("\"status\":\"PASSED\"")
        .contains("\"violationCount\":0,\"advisoryCount\":3")
        .contains("CSS_CROSS_LAYER_DUPLICATE")
        .contains("CSS_HARDCODED_COLOR")
        .doesNotContainIgnoringCase("warning")
        .doesNotContain("[WARN]");
    assertThat(readJson(artifacts))
        .contains("\"warningCount\": 3")
        .contains("\"rule\": \"cross-layer-duplicate\"")
        .contains("\"rule\": \"hardcoded-color\"");
    assertThat(readText(artifacts)).contains("CSS ownership: PASS (3 warnings)").contains("[WARN]");
  }

  @Test
  void blockAndAdvisoryRulesKeepLegacyOrderAndSeverity() throws Exception {
    writeCss(
        "base.css",
        """
        :root { --space: 1px; }
        button:hover, :focus, * { color: #fff; }
        .card { color: red; }
        .state-panel { color: red; }
        """);
    writeCss(
        "shell.css",
        """
        .sessions-page { display: block; }
        .sd-shell .state-panel { display: block; }
        """);
    writeCss("tokens.css", ":root { --color: #123456; }\n.token-class { color: red; }\n");
    writeCss("ui-primitives.css", ".sd-page { display: block; }\n");
    writeCss("z-page.css", ".btn { color: #123abc; }\n.btn:hover { color: #fff; }\n");
    var artifacts = artifactRoot("mixed");

    var result = run(artifacts);

    assertThat(result.exitCode()).isEqualTo(QualityGateExitCodes.VIOLATIONS);
    assertThat(result.out())
        .contains("\"violationCount\":5")
        .contains("\"advisoryCount\":4")
        .contains("\"status\":\"FAILED\"");
    assertThat(readJson(artifacts))
        .contains("\"filesScanned\": 5")
        .contains("\"selectorsAnalyzed\": 11")
        .contains("\"blockCount\": 5")
        .contains("\"warningCount\": 4")
        .containsSubsequence(
            "base.css 包含非元素选择器",
            "shell.css 包含页面级选择器",
            "tokens.css 不得包含选择器规则",
            "ui-primitives.css 包含页面级选择器",
            "dependency-direction",
            "cross-layer-duplicate",
            "hardcoded-color");
  }

  @Test
  void parserKeepsCommentOffsetNestedClosingOrderAndParenthesizedComma() throws Exception {
    writeCss(
        "page.css",
        """
        /* 第一行
        第二行 */
        .outer:is(.a, .b) {
          color: #112233;
          .btn { color: #445566; }
        }
        """);
    var artifacts = artifactRoot("parser");

    var result = run(artifacts);
    var json = readJson(artifacts);

    assertThat(result.exitCode()).isZero();
    assertThat(json)
        .contains("\"selectorsAnalyzed\": 2")
        .contains("\"warningCount\": 4")
        .contains("\"line\": 4")
        .contains("\"line\": 1")
        .containsSubsequence("cross-layer-duplicate", "#445566", "#112233", "#445566");
  }

  @Test
  void normalizesCrLfAndCrLikePythonUniversalNewlines() throws Exception {
    writeCss("page.css", "a\r\n{color:#123456}\r.btn{color:#abcdef}\r\n");
    var artifacts = artifactRoot("universal-newlines");

    var result = run(artifacts);
    var json = readJson(artifacts);

    assertThat(result.exitCode()).isZero();
    assertThat(json)
        .contains("\"warningCount\": 3")
        .contains("\"rule\": \"cross-layer-duplicate\"")
        .contains("\"line\": 2")
        .doesNotContain("\"line\": 3");
  }

  @Test
  void ignoresNestedCssAndWarnsEvenWithoutPrimitiveDefinition() throws Exception {
    Files.createDirectories(cssRoot().resolve("nested"));
    Files.writeString(cssRoot().resolve("nested/ignored.css"), ".btn { color:#123456; }\n");
    writeCss("page.css", ".btn { color: #fff; }\n");
    var artifacts = artifactRoot("top-level");

    var result = run(artifacts);

    assertThat(result.exitCode()).isZero();
    assertThat(readJson(artifacts))
        .contains("\"filesScanned\": 1")
        .contains("\"warningCount\": 1")
        .doesNotContain("ignored.css");
  }

  @Test
  void includesTopLevelSymbolicLinksAndFailsClosedForBrokenLinks() throws Exception {
    Files.createDirectories(cssRoot());
    var target = repo.resolve("external/linked-target.txt");
    Files.createDirectories(target.getParent());
    Files.writeString(target, ".btn { color: #123456; }\n", StandardCharsets.UTF_8);
    Files.createSymbolicLink(cssRoot().resolve("linked.css"), target);
    var linkedArtifacts = artifactRoot("linked");

    var linked = run(linkedArtifacts);

    assertThat(linked.exitCode()).isZero();
    assertThat(readJson(linkedArtifacts))
        .contains("\"filesScanned\": 1")
        .contains("\"warningCount\": 2")
        .contains("\"file\": \"linked.css\"");

    Files.delete(cssRoot().resolve("linked.css"));
    Files.createSymbolicLink(cssRoot().resolve("broken.css"), repo.resolve("missing-target.css"));
    var brokenArtifacts = artifactRoot("broken-link");
    var broken = run(brokenArtifacts);

    assertThat(broken.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(broken.err()).contains("failed closed");
    assertThat(brokenArtifacts.resolve("css-ownership")).doesNotExist();
  }

  @Test
  void sortsSupplementaryAndBmpFileNamesByPythonCodePointOrder() throws Exception {
    var supplementaryName = new String(Character.toChars(0x10000)) + ".css";
    var privateUseName = "\uE000.css";
    writeCss(supplementaryName, ".btn { color: #fff; }\n");
    writeCss(privateUseName, ".card { color: #fff; }\n");
    var artifacts = artifactRoot("unicode-order");

    var result = run(artifacts);
    var json = readJson(artifacts);

    assertThat(result.exitCode()).isZero();
    assertThat(json.indexOf(privateUseName)).isLessThan(json.indexOf(supplementaryName));
    assertThat(json).contains("\"filesScanned\": 2").contains("\"warningCount\": 2");
  }

  @Test
  void artifactsAreIsolatedAndByteStableAcrossRuns() throws Exception {
    writeCss("page.css", ".btn { color: #123456; }\n");
    var firstRoot = artifactRoot("run-a");
    var secondRoot = artifactRoot("run-b");

    assertThat(run(firstRoot).exitCode()).isZero();
    assertThat(run(secondRoot).exitCode()).isZero();

    assertThat(Files.readAllBytes(jsonPath(firstRoot)))
        .containsExactly(Files.readAllBytes(jsonPath(secondRoot)));
    assertThat(Files.readAllBytes(textPath(firstRoot)))
        .containsExactly(Files.readAllBytes(textPath(secondRoot)));
    assertThat(run(firstRoot).exitCode()).isZero();
    assertThat(Files.readAllBytes(jsonPath(firstRoot)))
        .containsExactly(Files.readAllBytes(jsonPath(secondRoot)));
    assertThat(Files.readAllBytes(textPath(firstRoot)))
        .containsExactly(Files.readAllBytes(textPath(secondRoot)));
    assertThat(firstRoot.resolve("css-ownership")).isDirectory();
    assertThat(secondRoot.resolve("css-ownership")).isDirectory();
  }

  @Test
  void directRunUsesBoundedRepoLocalPidFallback() throws Exception {
    Files.createDirectories(cssRoot());

    var result = runWithEnvironment(Map.of());

    var expected =
        repo.resolve("tmp/quality/direct/pid-" + ProcessHandle.current().pid())
            .resolve("css-ownership/css-ownership-gate.json");
    assertThat(result.exitCode()).isZero();
    assertThat(expected).isRegularFile();
  }

  @Test
  void rejectsRelativeArtifactRootAndMalformedUtf8() throws Exception {
    Files.createDirectories(cssRoot());
    var relative = runWithEnvironment(Map.of("FEIPI_QUALITY_ARTIFACT_DIR", "relative/path"));
    Files.write(cssRoot().resolve("bad.css"), new byte[] {(byte) 0xC3, (byte) 0x28});
    var malformedRoot = artifactRoot("malformed");
    var malformed = run(malformedRoot);

    assertThat(relative.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(relative.err()).contains("FEIPI_QUALITY_ARTIFACT_DIR must be absolute");
    assertThat(malformed.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(malformed.err()).contains("failed closed");
    assertThat(malformedRoot.resolve("css-ownership")).doesNotExist();
  }

  @Test
  void rejectsArtifactRootsOutsideBoundaryAndSymbolicLinkEscapes() throws Exception {
    Files.createDirectories(cssRoot());
    var external = repo.resolveSibling(repo.getFileName() + "-external");
    Files.createDirectories(external);
    var outside = run(external.resolve("run"));
    var normalizedEscape =
        runWithEnvironment(
            Map.of(
                "FEIPI_QUALITY_ARTIFACT_DIR",
                repo.resolve("tmp/quality/../../escaped").toString()));

    var qualityRoot = repo.resolve("tmp/quality");
    Files.createDirectories(qualityRoot);
    Files.createSymbolicLink(qualityRoot.resolve("linked"), external);
    var linked = run(qualityRoot.resolve("linked/run"));

    var safeRoot = artifactRoot("linked-output");
    Files.createDirectories(safeRoot);
    Files.createSymbolicLink(safeRoot.resolve("css-ownership"), external);
    var linkedOutput = run(safeRoot);

    assertThat(outside.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(normalizedEscape.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(linked.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(linkedOutput.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(outside.err()).contains("must stay within");
    assertThat(normalizedEscape.err()).contains("must stay within");
    assertThat(linked.err()).contains("contains symbolic link");
    assertThat(linkedOutput.err()).contains("must not be a symbolic link");
    assertThat(external.resolve("css-ownership-report.txt")).doesNotExist();
    assertThat(external.resolve("css-ownership-gate.json")).doesNotExist();
  }

  @Test
  void preparationFailureKeepsOldPairAndCleansStagingDirectory() throws Exception {
    var artifactRoot = artifactRoot("prepare-failure");
    var target = artifactRoot.resolve("css-ownership");
    writeOldPair(target);
    var writes = new AtomicInteger();
    var moves = new AtomicInteger();

    assertThatThrownBy(
            () ->
                ArtifactPairPublisher.publish(
                    target,
                    "css-ownership-report.txt",
                    "new text\n",
                    "css-ownership-gate.json",
                    "new json\n",
                    (path, content) -> {
                      if (writes.incrementAndGet() == 2) {
                        throw new IOException("injected prepare failure");
                      }
                      Files.write(path, content);
                    },
                    (source, destination) -> {
                      moves.incrementAndGet();
                      Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE);
                    }))
        .isInstanceOf(IOException.class)
        .hasMessageContaining("injected prepare failure");

    assertThat(moves).hasValue(0);
    assertOldPair(target);
    assertThat(directoryEntries(artifactRoot)).containsExactly("css-ownership");
  }

  @Test
  void publishFailureRestoresOldPairAndCleansTemporaryDirectories() throws Exception {
    var artifactRoot = artifactRoot("publish-failure");
    var target = artifactRoot.resolve("css-ownership");
    writeOldPair(target);
    var moves = new AtomicInteger();

    assertThatThrownBy(
            () ->
                ArtifactPairPublisher.publish(
                    target,
                    "css-ownership-report.txt",
                    "new text\n",
                    "css-ownership-gate.json",
                    "new json\n",
                    Files::write,
                    (source, destination) -> {
                      if (moves.incrementAndGet() == 2) {
                        throw new IOException("injected publish failure");
                      }
                      Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE);
                    }))
        .isInstanceOf(IOException.class)
        .hasMessageContaining("injected publish failure");

    assertThat(moves).hasValue(3);
    assertOldPair(target);
    assertThat(directoryEntries(artifactRoot)).containsExactly("css-ownership");
  }

  private Result run(Path artifactRoot) {
    return runWithEnvironment(Map.of("FEIPI_QUALITY_ARTIFACT_DIR", artifactRoot.toString()));
  }

  private Result runWithEnvironment(Map<String, String> environment) {
    var out = new ByteArrayOutputStream();
    var err = new ByteArrayOutputStream();
    var args =
        new String[] {
          "--repo-root",
          repo.toString(),
          "--paths",
          cssRoot().toString(),
          "--rules",
          "css-ownership"
        };
    var exitCode =
        QualityGateCli.run(
            args,
            environment,
            new PrintStream(err, true, StandardCharsets.UTF_8),
            new PrintStream(out, true, StandardCharsets.UTF_8));
    return new Result(
        exitCode, out.toString(StandardCharsets.UTF_8), err.toString(StandardCharsets.UTF_8));
  }

  private Path writeCss(String fileName, String content) throws Exception {
    var path = cssRoot().resolve(fileName);
    Files.createDirectories(path.getParent());
    Files.writeString(path, content, StandardCharsets.UTF_8);
    return path;
  }

  private Path cssRoot() {
    return repo.resolve(CSS_ROOT);
  }

  private Path artifactRoot(String name) {
    return repo.resolve("tmp/quality/tests").resolve(name);
  }

  private static void writeOldPair(Path target) throws Exception {
    Files.createDirectories(target);
    Files.writeString(target.resolve("css-ownership-report.txt"), "old text\n");
    Files.writeString(target.resolve("css-ownership-gate.json"), "old json\n");
  }

  private static void assertOldPair(Path target) throws Exception {
    assertThat(Files.readString(target.resolve("css-ownership-report.txt")))
        .isEqualTo("old text\n");
    assertThat(Files.readString(target.resolve("css-ownership-gate.json"))).isEqualTo("old json\n");
  }

  private static java.util.List<String> directoryEntries(Path directory) throws Exception {
    try (var entries = Files.list(directory)) {
      return entries.map(path -> path.getFileName().toString()).sorted().toList();
    }
  }

  private static String readJson(Path artifactRoot) throws Exception {
    return Files.readString(jsonPath(artifactRoot), StandardCharsets.UTF_8);
  }

  private static String readText(Path artifactRoot) throws Exception {
    return Files.readString(textPath(artifactRoot), StandardCharsets.UTF_8);
  }

  private static Path jsonPath(Path artifactRoot) {
    return artifactRoot.resolve("css-ownership/css-ownership-gate.json");
  }

  private static Path textPath(Path artifactRoot) {
    return artifactRoot.resolve("css-ownership/css-ownership-report.txt");
  }

  /**
   * CLI 调用结果。
   *
   * @param exitCode 进程语义退出码。
   * @param out 标准输出。
   * @param err 标准错误。
   */
  private record Result(int exitCode, String out, String err) {}
}
