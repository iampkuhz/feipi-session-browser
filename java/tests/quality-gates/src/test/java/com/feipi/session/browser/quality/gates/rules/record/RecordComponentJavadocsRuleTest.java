package com.feipi.session.browser.quality.gates.rules.record;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.quality.gates.core.JavaSourceSet;
import com.feipi.session.browser.quality.gates.core.QualityContext;
import com.feipi.session.browser.quality.gates.core.RepositorySourceSet;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

/** 保留 nested/generic/annotation 与多违规的高价值 corpus。 */
class RecordComponentJavadocsRuleTest {

  @Test
  void compilerDocTreesPreservesFixtureViolationKeys() throws Exception {
    var repo = Path.of("").toAbsolutePath();
    var fixtures = repo.resolve("src/test/resources/fixtures/record-component-javadocs");
    try (var paths = Files.walk(fixtures)) {
      var sources = paths.filter(path -> path.toString().endsWith(".java")).sorted().toList();
      var sourceSet = JavaSourceSet.parse(repo, sources);
      var violations =
          new RecordComponentJavadocsRule()
              .check(
                  new QualityContext(
                      repo,
                      sourceSet,
                      new RepositorySourceSet(java.util.List.of()),
                      repo.resolve("unused"),
                      false,
                      repo.resolve("tmp/quality/test")));

      assertThat(violations).hasSize(6);
      assertThat(violations)
          .extracting(item -> item.code())
          .containsExactlyInAnyOrderElementsOf(
              List.of(
                  "RECORD_COMPONENT_PARAM_MISSING",
                  "RECORD_COMPONENT_PARAM_NOT_CHINESE",
                  "RECORD_COMPONENT_PARAM_NOT_CHINESE",
                  "RECORD_JAVADOC_MISSING",
                  "RECORD_JAVADOC_MISSING",
                  "RECORD_COMPONENT_PARAM_MISSING"));
    }
  }
}
