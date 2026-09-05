package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.scan.engine.ScanConfig;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

/** scan 与 serve 的默认源目录选择契约，不读取真实用户目录。 */
@ResourceLock(Resources.SYSTEM_PROPERTIES)
class SourceDirectoriesTest {

  @TempDir Path home;
  private String originalHome;

  @BeforeEach
  void isolateHome() {
    originalHome = System.getProperty("user.home");
    System.setProperty("user.home", home.toString());
  }

  @AfterEach
  void restoreHome() {
    System.setProperty("user.home", originalHome);
  }

  @Test
  void bothCommandsSelectAllDefaultDirectories() throws Exception {
    List<Path> roots =
        List.of(home.resolve(".claude"), home.resolve(".codex"), home.resolve(".qoder"));
    for (Path root : roots) {
      Files.createDirectories(root);
    }

    assertThat(scanRoots(Set.of())).containsExactlyElementsOf(roots);
    assertThat(serveRoots(Set.of())).containsExactlyElementsOf(roots);
  }

  @Test
  void bothCommandsApplyAgentFilter() throws Exception {
    Files.createDirectories(home.resolve(".claude"));
    Files.createDirectories(home.resolve(".codex"));
    Files.createDirectories(home.resolve(".qoder"));

    for (String agent : List.of("claude_code", "codex", "qoder")) {
      Path expected = home.resolve(agent.equals("claude_code") ? ".claude" : "." + agent);
      assertThat(scanRoots(Set.of(agent))).containsExactly(expected);
      assertThat(serveRoots(Set.of(agent))).containsExactly(expected);
    }
  }

  @Test
  void missingDirectoriesAndRegularFilesAreNotSources() throws Exception {
    Files.createFile(home.resolve(".claude"));
    assertThat(scanRoots(Set.of())).isEmpty();
    assertThat(serveRoots(Set.of())).isEmpty();
  }

  private List<Path> scanRoots(Set<String> filter) throws Exception {
    Method method = ScanCommand.class.getDeclaredMethod("buildSourceEntries", Set.class);
    method.setAccessible(true);
    return roots(method.invoke(new ScanCommand(), filter));
  }

  private List<Path> serveRoots(Set<String> filter) throws Exception {
    ServerLifecycle lifecycle =
        new ServerLifecycle(home.resolve("index"), "127.0.0.1", 0, true, true, filter);
    Method method = ServerLifecycle.class.getDeclaredMethod("buildSourceEntries", Path.class);
    method.setAccessible(true);
    return roots(method.invoke(lifecycle, home.resolve("artifacts")));
  }

  private static List<Path> roots(Object entries) {
    return ((List<?>) entries)
        .stream()
            .map(ScanConfig.SourceEntry.class::cast)
            .map(ScanConfig.SourceEntry::rootPath)
            .toList();
  }
}
