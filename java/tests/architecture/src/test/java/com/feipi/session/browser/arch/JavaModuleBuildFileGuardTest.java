package com.feipi.session.browser.arch;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Gradle 文本级模块边界守卫。
 *
 * <p>ArchUnit 能检查字节码依赖，但不能看到 {@code settings.gradle.kts} 和生产 Gradle 依赖声明，因此这里对构建文件做最小文本检查。
 */
@DisplayName("Java module Gradle boundary guards")
final class JavaModuleBuildFileGuardTest {

  private static final Pattern PRODUCTION_PROJECT_DEPENDENCY =
      Pattern.compile(
          "^(api|implementation|compileOnly|runtimeOnly|annotationProcessor)\\s*\\(\\s*project\\(\\s*(?:path\\s*=\\s*)?\"([^\"]+)\"");

  private JavaModuleBuildFileGuardTest() {}

  /** settings 不得重新 include 已删除/替换的模块。 */
  @Test
  @DisplayName("settings.gradle.kts must not include removed Java modules")
  void settingsMustNotIncludeRemovedModules() throws IOException {
    String settings = readRepoFile("java/settings.gradle.kts");

    assertThat(settings)
        .as("settings.gradle.kts must not include :java:artifact-normalized")
        .doesNotContain("\"java:artifact-normalized\"");
    assertThat(settings)
        .as("settings.gradle.kts must not include legacy :java:index-sqlite")
        .doesNotContain("\"java:index-sqlite\"");
    assertThat(settings)
        .as("settings.gradle.kts must include the abstract :java:index-api module")
        .contains("\"java:index-api\"");
  }

  /** application/web/scan-engine 的生产依赖不得重新指向具体 store 或 sources。 */
  @Test
  @DisplayName("production build.gradle.kts dependencies must not bypass API modules")
  void productionBuildFilesMustNotDependOnForbiddenModules() throws IOException {
    assertNoProductionProjectDeps(
        "java/application/build.gradle.kts",
        Set.of(":java:index-store-sqlite", ":java:index-sqlite"));
    assertNoProductionProjectDeps(
        "java/web/build.gradle.kts", Set.of(":java:index-store-sqlite", ":java:index-sqlite"));
    assertNoProductionProjectDeps(
        "java/scan-engine/build.gradle.kts",
        Set.of(":java:index-store-sqlite", ":java:index-sqlite", ":java:sources"));
  }

  private static void assertNoProductionProjectDeps(String relativePath, Set<String> forbidden)
      throws IOException {
    List<String> violations = new ArrayList<>();
    List<String> lines = Files.readAllLines(repoRoot().resolve(relativePath));
    for (int index = 0; index < lines.size(); index++) {
      String line = lines.get(index).strip();
      Matcher matcher = PRODUCTION_PROJECT_DEPENDENCY.matcher(line);
      if (matcher.find() && forbidden.contains(matcher.group(2))) {
        violations.add((index + 1) + ": " + line);
      }
    }

    assertThat(violations)
        .as(
            "%s must not declare production project dependencies on %s; depend on abstract ports"
                + " instead",
            relativePath, forbidden)
        .isEmpty();
  }

  private static String readRepoFile(String relativePath) throws IOException {
    return Files.readString(repoRoot().resolve(relativePath));
  }

  private static Path repoRoot() {
    return Path.of(System.getProperty("repo.root.dir"));
  }
}
