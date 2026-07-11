package com.feipi.session.browser.quality.gates.discovery;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link FileDiscovery} 单元测试。 */
class FileDiscoveryTest {

  @TempDir Path tempDir;

  @Test
  void discoversMainJavaSources() throws IOException {
    // 创建 src/main/java 结构
    var mainJava = tempDir.resolve("a/src/main/java");
    Files.createDirectories(mainJava);
    var javaFile = mainJava.resolve("Foo.java");
    Files.writeString(javaFile, "class Foo {}", StandardCharsets.UTF_8);

    var result = FileDiscovery.discover(List.of(tempDir.resolve("a")));
    assertThat(result).containsExactly(javaFile);
  }

  @Test
  void excludesBuildDirectory() throws IOException {
    var buildJava = tempDir.resolve("a/build/src/main/java");
    Files.createDirectories(buildJava);
    Files.writeString(buildJava.resolve("Build.java"), "class Build {}", StandardCharsets.UTF_8);

    var result = FileDiscovery.discover(List.of(tempDir.resolve("a")));
    assertThat(result).isEmpty();
  }

  @Test
  void excludesTestSources() throws IOException {
    var testJava = tempDir.resolve("a/src/test/java");
    Files.createDirectories(testJava);
    Files.writeString(testJava.resolve("Test.java"), "class Test {}", StandardCharsets.UTF_8);

    var result = FileDiscovery.discover(List.of(tempDir.resolve("a")));
    assertThat(result).isEmpty();
  }

  @Test
  void acceptsSingleFile() throws IOException {
    var file = tempDir.resolve("Standalone.java");
    Files.writeString(file, "class Standalone {}", StandardCharsets.UTF_8);

    var result = FileDiscovery.discover(List.of(file));
    assertThat(result).containsExactly(file);
  }

  @Test
  void isMainJavaSourceDetectsCorrectly() {
    assertThat(FileDiscovery.isMainJavaSource(Path.of("a/src/main/java/Foo.java"))).isTrue();
    assertThat(FileDiscovery.isMainJavaSource(Path.of("a/b/src/main/java/c/Foo.java"))).isTrue();
    assertThat(FileDiscovery.isMainJavaSource(Path.of("a/src/test/java/Foo.java"))).isFalse();
    assertThat(FileDiscovery.isMainJavaSource(Path.of("a/src/main/Foo.java"))).isFalse();
  }
}
