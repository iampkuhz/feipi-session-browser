package com.feipi.session.browser.quality.gates.cli;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 唯一 Java CLI 的 Web baseline 单/双 rule 原子维护 contract。 */
class WebBaselineUpdateCliTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String BASELINE =
      "java/tests/quality-gates/config/web-quality-baselines.json";

  @TempDir Path repo;

  @Test
  void singleRuleUpdatePreservesOtherSectionsAndIsByteStable() throws Exception {
    writeCanonicalBaseline(
        "[\"stale.js:9\"]", "[\"keep-layout.html:7\"]", "[\"keep-static-selector\"]");
    write("java/web/src/main/resources/static/js/current.js", "node.innerHTML = value;\n");
    var before = readBaseline();

    var first = update("raw-innerhtml", "raw-innerhtml");
    var firstBytes = Files.readAllBytes(repo.resolve(BASELINE));
    var updated = readBaseline();
    var second = update("raw-innerhtml", "raw-innerhtml");

    assertThat(first.exitCode()).isZero();
    assertThat(second.exitCode()).isZero();
    assertThat(repo.resolve("config/web-quality-baselines.json")).doesNotExist();
    assertThat(first.out())
        .contains("\"rule\":\"raw-innerhtml\"")
        .contains("\"status\":\"PASSED\"");
    assertThat(updated.path("rules").path("static-resource-contract"))
        .isEqualTo(before.path("rules").path("static-resource-contract"));
    assertThat(updated.path("rules").path("layout-inline-style"))
        .isEqualTo(before.path("rules").path("layout-inline-style"));
    assertThat(updated.path("rules").path("raw-innerhtml").path("entries"))
        .containsExactly(
            MAPPER.getNodeFactory().textNode("java/web/src/main/resources/static/js/current.js:1"));
    assertThat(Files.readAllBytes(repo.resolve(BASELINE))).isEqualTo(firstBytes);
    assertThat(new String(firstBytes, StandardCharsets.UTF_8)).doesNotEndWith("\n");
    var firstText = new String(firstBytes, StandardCharsets.UTF_8);
    assertThat(firstText.indexOf("static-resource-contract"))
        .isLessThan(firstText.indexOf("raw-innerhtml"));
    assertThat(firstText.indexOf("raw-innerhtml"))
        .isLessThan(firstText.indexOf("layout-inline-style"));
  }

  @Test
  void dualRuleUpdateIsAtomicAndIndependentOfRequestedRuleOrder() throws Exception {
    writeCanonicalBaseline("[\"stale.js:9\"]", "[\"stale.html:8\"]", "[\"keep-static-selector\"]");
    write("tests/browser.js", "test.innerHTML = value;\n");
    write(
        "java/web/src/main/resources/templates/page.html",
        "<div style=\"display:grid\">page</div>\n");
    var beforeStatic = readBaseline().path("rules").path("static-resource-contract").deepCopy();

    var reverse = update("layout-inline-style,raw-innerhtml", "layout-inline-style,raw-innerhtml");
    var reverseBytes = Files.readAllBytes(repo.resolve(BASELINE));
    var forward = update("raw-innerhtml,layout-inline-style", "raw-innerhtml,layout-inline-style");
    var updated = readBaseline();

    assertThat(reverse.exitCode()).isZero();
    assertThat(forward.exitCode()).isZero();
    assertThat(repo.resolve("config/web-quality-baselines.json")).doesNotExist();
    assertThat(forward.out())
        .contains("\"rule\":\"raw-innerhtml\"")
        .contains("\"rule\":\"layout-inline-style\"");
    assertThat(Files.readAllBytes(repo.resolve(BASELINE))).isEqualTo(reverseBytes);
    assertThat(updated.path("rules").path("static-resource-contract")).isEqualTo(beforeStatic);
    assertThat(updated.path("rules").path("raw-innerhtml").path("entries").get(0).asText())
        .isEqualTo("tests/browser.js:1");
    assertThat(updated.path("rules").path("layout-inline-style").path("entries").get(0).asText())
        .isEqualTo("java/web/src/main/resources/templates/page.html:1");
  }

  @Test
  void emptyScanReplacesOnlyTheSelectedSectionWithAnEmptyList() throws Exception {
    writeCanonicalBaseline(
        "[\"keep-raw.js:3\"]", "[\"stale-layout.html:4\"]", "[\"keep-static-selector\"]");

    var result = update("layout-inline-style", "layout-inline-style");
    var updated = readBaseline();

    assertThat(result.exitCode()).isZero();
    assertThat(updated.path("rules").path("layout-inline-style").path("entries")).isEmpty();
    assertThat(updated.path("rules").path("raw-innerhtml").path("entries").get(0).asText())
        .isEqualTo("keep-raw.js:3");
  }

  @Test
  void updateIgnoresChangedFilesAndDeduplicatesMultipleFindingsOnOneLine() throws Exception {
    writeCanonicalBaseline("[]", "[]", "[]");
    write("tests/browser.js", "test.innerHTML = value;\n");
    write(
        "java/web/src/main/resources/templates/page.html",
        "<div style=\"display:grid\"><span style=\"margin:0\">page</span></div>\n");

    var result =
        update(
            "raw-innerhtml,layout-inline-style",
            "raw-innerhtml,layout-inline-style",
            Map.of("QUALITY_CHANGED_FILES", "[\"README.md\"]"));
    var updated = readBaseline();

    assertThat(result.exitCode()).isZero();
    assertThat(updated.path("rules").path("raw-innerhtml").path("entries"))
        .containsExactly(MAPPER.getNodeFactory().textNode("tests/browser.js:1"));
    assertThat(updated.path("rules").path("layout-inline-style").path("entries"))
        .containsExactly(
            MAPPER.getNodeFactory().textNode("java/web/src/main/resources/templates/page.html:1"));
  }

  @Test
  void missingBaselineIsCreatedByEveryExplicitUpdate() throws Exception {
    Files.deleteIfExists(repo.resolve(BASELINE));
    write("scripts/browser.js", "node.innerHTML = value;\n");

    var first = update("raw-innerhtml", "raw-innerhtml");
    var firstBytes = Files.readAllBytes(repo.resolve(BASELINE));
    var second = update("raw-innerhtml", "raw-innerhtml");

    assertThat(first.exitCode()).isZero();
    assertThat(second.exitCode()).isZero();
    assertThat(repo.resolve("config/web-quality-baselines.json")).doesNotExist();
    assertThat(repo.resolve("config")).doesNotExist();
    assertThat(Files.readAllBytes(repo.resolve(BASELINE))).isEqualTo(firstBytes);
    assertThat(readBaseline().path("version").asInt()).isEqualTo(1);
    assertThat(readBaseline().path("rules").path("raw-innerhtml").path("entries"))
        .containsExactly(MAPPER.getNodeFactory().textNode("scripts/browser.js:1"));
  }

  @Test
  void invalidRuleSelectionOrMalformedUpdatesFailBeforeReplacingTheSharedFile() throws Exception {
    writeCanonicalBaseline("[]", "[]", "[]");
    var original = Files.readAllBytes(repo.resolve(BASELINE));

    var unknown = update("raw-innerhtml", "missing-rule");
    var capabilityMissing = update("static-resource-contract", "static-resource-contract");
    var capabilityCheckedBeforeChangedFiles =
        update(
            "record-component-javadocs",
            "record-component-javadocs",
            Map.of("QUALITY_CHANGED_FILES", "not-json"));
    var mismatch = update("raw-innerhtml,layout-inline-style", "raw-innerhtml");
    var empty = update("raw-innerhtml", ",, ");

    assertThat(unknown.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(capabilityMissing.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(capabilityMissing.err()).contains("Baseline update capability required");
    assertThat(capabilityCheckedBeforeChangedFiles.exitCode())
        .isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(capabilityCheckedBeforeChangedFiles.err())
        .contains("Baseline update capability required")
        .doesNotContain("changed-files");
    assertThat(mismatch.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(empty.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(empty.err()).contains("requires at least one rule");
    assertThat(Files.readAllBytes(repo.resolve(BASELINE))).isEqualTo(original);

    Files.writeString(repo.resolve(BASELINE), "{not-json", StandardCharsets.UTF_8);
    var malformedBytes = Files.readAllBytes(repo.resolve(BASELINE));
    var malformed = update("raw-innerhtml", "raw-innerhtml");

    assertThat(malformed.exitCode()).isEqualTo(QualityGateExitCodes.ERROR);
    assertThat(Files.readAllBytes(repo.resolve(BASELINE))).isEqualTo(malformedBytes);
  }

  @Test
  void everyInvalidSharedBaselineSchemaFailsWithoutReplacement() throws Exception {
    var invalidDocuments =
        List.of(
            "[]",
            "{\"version\":1,\"version\":1,\"rules\":{}}",
            "{\"version\":1,\"rules\":{}} {}",
            "{\"version\":4294967297,\"rules\":{}}",
            "{\"version\":2,\"rules\":{}}",
            "{\"version\":1,\"rules\":[],\"extra\":true}",
            "{\"version\":1,\"rules\":{},\"extra\":true}",
            "{\"version\":1,\"rules\":{\"raw-innerhtml\":[]}}",
            "{\"version\":1,\"rules\":{\"raw-innerhtml\":{\"entries\":\"bad\"}}}",
            "{\"version\":1,\"rules\":{\"raw-innerhtml\":{\"entries\":[1]}}}");

    for (var invalid : invalidDocuments) {
      write(BASELINE, invalid);
      var original = Files.readAllBytes(repo.resolve(BASELINE));

      var result = update("raw-innerhtml", "raw-innerhtml");

      assertThat(result.exitCode()).as(invalid).isEqualTo(QualityGateExitCodes.ERROR);
      assertThat(Files.readAllBytes(repo.resolve(BASELINE))).as(invalid).isEqualTo(original);
    }
  }

  @Test
  void atomicMoveFailureFailsClosedAndPreservesOriginal() throws Exception {
    writeCanonicalBaseline("[]", "[]", "[]");
    var baseline = repo.resolve(BASELINE);
    var original = Files.readAllBytes(baseline);
    var replacement = Map.of("raw-innerhtml", Map.of("entries", List.of("new.js:1")));

    assertThatThrownBy(
            () ->
                BaselineUpdateWriter.mergeAndWrite(
                    baseline,
                    replacement,
                    (source, target) -> {
                      throw new AtomicMoveNotSupportedException(
                          source.toString(), target.toString(), "fixture");
                    }))
        .isInstanceOf(AtomicMoveNotSupportedException.class);

    assertThat(Files.readAllBytes(baseline)).isEqualTo(original);
    try (var files = Files.list(baseline.getParent())) {
      assertThat(files.map(path -> path.getFileName().toString()).toList())
          .noneMatch(name -> name.endsWith(".tmp"));
    }
  }

  private Result update(String rules, String updateRules) {
    return update(rules, updateRules, Map.of());
  }

  private Result update(String rules, String updateRules, Map<String, String> environment) {
    var args = new ArrayList<String>();
    java.util.Collections.addAll(
        args,
        "--repo-root",
        repo.toString(),
        "--paths",
        repo.toString(),
        "--rules",
        rules,
        "--update-baselines",
        updateRules);
    var out = new ByteArrayOutputStream();
    var err = new ByteArrayOutputStream();
    var exitCode =
        QualityGateCli.run(
            args.toArray(String[]::new),
            environment,
            new PrintStream(err, true, StandardCharsets.UTF_8),
            new PrintStream(out, true, StandardCharsets.UTF_8));
    return new Result(
        exitCode, out.toString(StandardCharsets.UTF_8), err.toString(StandardCharsets.UTF_8));
  }

  private JsonNode readBaseline() throws Exception {
    return MAPPER.readTree(repo.resolve(BASELINE).toFile());
  }

  private void writeCanonicalBaseline(String raw, String layout, String staticEntries)
      throws Exception {
    write(
        BASELINE,
        """
        {
          "version": 1,
          "rules": {
            "static-resource-contract": {
              "selector_depth_violations": %s,
              "component_override_violations": []
            },
            "raw-innerhtml": {"entries": %s},
            "layout-inline-style": {"entries": %s}
          }
        }
        """
            .formatted(staticEntries, raw, layout));
  }

  private Path write(String relativePath, String content) throws Exception {
    var path = repo.resolve(relativePath);
    Files.createDirectories(path.getParent());
    return Files.writeString(path, content, StandardCharsets.UTF_8);
  }

  private record Result(int exitCode, String out, String err) {}
}
