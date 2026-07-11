package com.feipi.session.browser.quality.gates.discovery;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

/** {@link ChangedFilesFilter} 单元测试。 */
class ChangedFilesFilterTest {

  @Test
  void nullJsonReturnsOriginalList() {
    var files = List.of(Path.of("a/src/main/java/X.java"));
    var result = ChangedFilesFilter.filter(files, null, Path.of(""));
    assertThat(result).isSameAs(files);
  }

  @Test
  void emptyJsonReturnsOriginalList() {
    var files = List.of(Path.of("a/src/main/java/X.java"));
    var result = ChangedFilesFilter.filter(files, "", Path.of(""));
    assertThat(result).isSameAs(files);
  }

  @Test
  void invalidJsonReturnsOriginalList() {
    var files = List.of(Path.of("a/src/main/java/X.java"));
    var result = ChangedFilesFilter.filter(files, "not-json", Path.of(""));
    assertThat(result).isSameAs(files);
  }

  @Test
  void parseChangedFilesExtractsJavaPaths() {
    var paths =
        ChangedFilesFilter.parseChangedFiles(
            "[\"a/src/main/java/X.java\", \"b/src/test/java/Y.java\"]", Path.of(""));
    assertThat(paths).containsExactly("a/src/main/java/X.java");
  }

  @Test
  void parseChangedFilesRejectsNonJava() {
    var paths = ChangedFilesFilter.parseChangedFiles("[\"a/src/main/java/X.kt\"]", Path.of(""));
    assertThat(paths).isEmpty();
  }
}
