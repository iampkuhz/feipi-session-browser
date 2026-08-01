package com.feipi.session.browser.quality.gates.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 仓库 source discovery 对运行目录剪枝与业务源码 fail-closed 的 contract。 */
class RepositorySourceSetTest {

  @TempDir Path repo;

  @Test
  void volatileRuntimeDirectoriesArePrunedBeforeFileSelection() throws Exception {
    for (var directory : List.of("build", ".gradle", "node_modules", "__pycache__")) {
      write("java/module/" + directory + "/generated.js", "ignored\n");
    }
    write("java/module/src/owned.js", "owned\n");

    var sources =
        RepositorySourceSet.discover(
            repo, List.of(repo.resolve("java")), path -> path.endsWith(".js"));

    assertThat(sources.sources())
        .extracting(RepositorySourceSet.SourceText::relativePath)
        .containsExactly("java/module/src/owned.js");
  }

  @Test
  void supportedBusinessSourceDisappearingDuringDiscoveryFailsClosed() throws Exception {
    var source = write("scripts/business.js", "owned\n");

    assertThatThrownBy(
            () ->
                RepositorySourceSet.discover(
                    repo,
                    List.of(source),
                    path -> {
                      assertThat(source.toFile().delete()).isTrue();
                      return true;
                    }))
        .isInstanceOf(NoSuchFileException.class);
  }

  private Path write(String relativePath, String content) throws Exception {
    var path = repo.resolve(relativePath);
    Files.createDirectories(path.getParent());
    Files.writeString(path, content, StandardCharsets.UTF_8);
    return path;
  }
}
