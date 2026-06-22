package com.feipi.session.browser.source.qoder;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link QoderDiscovery} 单元测试。
 *
 * <p>验证会话发现逻辑在各种目录结构下的行为：空目录、 projects/ 结构、cache/projects/ 结构、 多项目多会话排序和隐藏文件过滤。
 */
@DisplayName("QoderDiscovery 会话发现测试")
class QoderDiscoveryTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("空目录和边界场景")
  class EmptyAndBoundary {

    @Test
    @DisplayName("空目录返回空列表")
    void emptyDirectoryReturnsEmptyList() {
      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("null 路径返回空列表")
    void nullPathReturnsEmptyList() {
      List<Path> sessions = QoderDiscovery.discoverSessions(null);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("无 projects 子目录返回空列表")
    void noProjectsSubdirReturnsEmptyList() throws IOException {
      Files.createDirectory(tempDir.resolve("other"));
      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }
  }

  @Nested
  @DisplayName("projects/ 目录发现")
  class ProjectsDiscovery {

    @Test
    @DisplayName("单层项目会话发现")
    void singleProjectSingleSession() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);
      Path sessionFile = projectDir.resolve("session-001.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }

    @Test
    @DisplayName("多项目多会话按路径确定性排序")
    void multipleProjectsMultipleSessionsSorted() throws IOException {
      Path projects = tempDir.resolve("projects");

      Path projectB = projects.resolve("project-b");
      Files.createDirectories(projectB);
      Path sessionB1 = projectB.resolve("beta.jsonl");
      Path sessionB2 = projectB.resolve("alpha.jsonl");
      Files.writeString(sessionB1, "{}\n", StandardCharsets.UTF_8);
      Files.writeString(sessionB2, "{}\n", StandardCharsets.UTF_8);

      Path projectA = projects.resolve("project-a");
      Files.createDirectories(projectA);
      Path sessionA1 = projectA.resolve("second.jsonl");
      Path sessionA2 = projectA.resolve("first.jsonl");
      Files.writeString(sessionA1, "{}\n", StandardCharsets.UTF_8);
      Files.writeString(sessionA2, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(4);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }
  }

  @Nested
  @DisplayName("cache/projects/ 目录发现")
  class CacheProjectsDiscovery {

    @Test
    @DisplayName("缓存目录会话发现")
    void cacheProjectSessions() throws IOException {
      Path cacheProjects = tempDir.resolve("cache").resolve("projects");
      Path projectDir = cacheProjects.resolve("cached-project");
      Files.createDirectories(projectDir);
      Path sessionFile = projectDir.resolve("cached-session.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }

    @Test
    @DisplayName("同时发现 projects/ 和 cache/projects/ 的会话")
    void bothProjectsAndCacheSessions() throws IOException {
      // projects/ 目录
      Path projects = tempDir.resolve("projects");
      Path mainProject = projects.resolve("main-project");
      Files.createDirectories(mainProject);
      Path mainSession = mainProject.resolve("main-session.jsonl");
      Files.writeString(mainSession, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      // cache/projects/ 目录
      Path cacheProjects = tempDir.resolve("cache").resolve("projects");
      Path cacheProject = cacheProjects.resolve("cache-project");
      Files.createDirectories(cacheProject);
      Path cacheSession = cacheProject.resolve("cache-session.jsonl");
      Files.writeString(cacheSession, "{\"type\":\"user\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }
  }

  @Nested
  @DisplayName("文件和目录过滤")
  class Filtering {

    @Test
    @DisplayName("跳过非 .jsonl 文件")
    void skipNonJsonlFiles() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      Path jsonlFile = projectDir.resolve("valid.jsonl");
      Path txtFile = projectDir.resolve("readme.txt");
      Path jsonFile = projectDir.resolve("config.json");
      Files.writeString(jsonlFile, "{}\n", StandardCharsets.UTF_8);
      Files.writeString(txtFile, "not a session", StandardCharsets.UTF_8);
      Files.writeString(jsonFile, "{}", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(jsonlFile);
    }

    @Test
    @DisplayName("跳过隐藏文件和隐藏目录")
    void skipHiddenFilesAndDirectories() throws IOException {
      Path projects = tempDir.resolve("projects");

      Path hiddenProject = projects.resolve(".hidden-project");
      Files.createDirectories(hiddenProject);
      Files.writeString(hiddenProject.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);

      Path normalProject = projects.resolve("normal-project");
      Files.createDirectories(normalProject);
      Path normalSession = normalProject.resolve("session.jsonl");
      Files.writeString(normalSession, "{}\n", StandardCharsets.UTF_8);

      Path hiddenFile = normalProject.resolve(".hidden.jsonl");
      Files.writeString(hiddenFile, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(normalSession);
    }

    @Test
    @DisplayName("跳过项目内的子目录")
    void skipSubdirectoriesInsideProject() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      Path sessionFile = projectDir.resolve("session.jsonl");
      Files.writeString(sessionFile, "{}\n", StandardCharsets.UTF_8);

      Path subDir = projectDir.resolve("subdir.jsonl");
      Files.createDirectory(subDir);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }
  }

  @Nested
  @DisplayName("排序")
  class Sorting {

    @Test
    @DisplayName("cache/projects/ 按字母序排在 projects/ 之前")
    void cacheBeforeProjects() throws IOException {
      // cache/projects/ 目录
      Path cacheProjects = tempDir.resolve("cache").resolve("projects");
      Path cacheProject = cacheProjects.resolve("project-x");
      Files.createDirectories(cacheProject);
      Path cacheSession = cacheProject.resolve("session.jsonl");
      Files.writeString(cacheSession, "{}\n", StandardCharsets.UTF_8);

      // projects/ 目录
      Path projects = tempDir.resolve("projects");
      Path mainProject = projects.resolve("project-a");
      Files.createDirectories(mainProject);
      Path mainSession = mainProject.resolve("session.jsonl");
      Files.writeString(mainSession, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = QoderDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      // 按路径字母序，cache/ 在 projects/ 之前
      assertThat(sessions.get(0)).isEqualTo(cacheSession);
      assertThat(sessions.get(1)).isEqualTo(mainSession);
    }
  }
}
