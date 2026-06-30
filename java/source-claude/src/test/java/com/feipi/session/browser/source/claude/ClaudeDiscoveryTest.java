package com.feipi.session.browser.source.claude;

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
 * {@link ClaudeDiscovery} 单元测试。
 *
 * <p>验证会话发现逻辑在各种目录结构下的行为：空目录、 单层结构、多项目多会话排序、隐藏文件过滤、
 * 递归发现嵌套子目录中的会话文件。
 */
@DisplayName("ClaudeDiscovery 会话发现测试")
class ClaudeDiscoveryTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("空目录和边界场景")
  class EmptyAndBoundary {

    @Test
    @DisplayName("空目录返回空列表")
    void emptyDirectoryReturnsEmptyList() {
      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("null 路径返回空列表")
    void nullPathReturnsEmptyList() {
      List<Path> sessions = ClaudeDiscovery.discoverSessions(null);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("无 projects 子目录返回空列表")
    void noProjectsSubdirReturnsEmptyList() throws IOException {
      Files.createDirectory(tempDir.resolve("other"));
      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }
  }

  @Nested
  @DisplayName("正常会话发现")
  class NormalDiscovery {

    @Test
    @DisplayName("单层项目会话发现")
    void singleProjectSingleSession() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);
      Path sessionFile = projectDir.resolve("session-001.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

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

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(4);
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

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

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

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(normalSession);
    }

    @Test
    @DisplayName("跳过项目内的子目录（目录名为 .jsonl 结尾也不包含）")
    void skipSubdirectoriesInsideProject() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      Path sessionFile = projectDir.resolve("session.jsonl");
      Files.writeString(sessionFile, "{}\n", StandardCharsets.UTF_8);

      Path subDir = projectDir.resolve("subdir.jsonl");
      Files.createDirectory(subDir);

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }
  }

  @Nested
  @DisplayName("递归发现嵌套会话")
  class RecursiveDiscovery {

    @Test
    @DisplayName("发现 subagents 子目录中的嵌套会话文件")
    void discoversSubagentSessions() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      // 主会话（直接子文件）
      Path mainSession = projectDir.resolve("session-001.jsonl");
      Files.writeString(mainSession, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      // subagent 嵌套会话：<session-id>/subagents/<agent-name>.jsonl
      Path subagentDir = projectDir.resolve("session-001").resolve("subagents");
      Files.createDirectories(subagentDir);
      Path subagentSession = subagentDir.resolve("implementer.jsonl");
      Files.writeString(subagentSession, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      assertThat(sessions).containsExactlyInAnyOrder(mainSession, subagentSession);
    }

    @Test
    @DisplayName("发现多层嵌套的会话文件")
    void discoversMultiLevelNestedSessions() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      // 直接子文件
      Path directSession = projectDir.resolve("root-session.jsonl");
      Files.writeString(directSession, "{}\n", StandardCharsets.UTF_8);

      // 2 层嵌套
      Path level2Dir = projectDir.resolve("session-a").resolve("subagents");
      Files.createDirectories(level2Dir);
      Path level2Session = level2Dir.resolve("agent-x.jsonl");
      Files.writeString(level2Session, "{}\n", StandardCharsets.UTF_8);

      // 4 层嵌套
      Path level4Dir = projectDir.resolve("session-b").resolve("subagents")
          .resolve("task-1").resolve("sub-tasks");
      Files.createDirectories(level4Dir);
      Path level4Session = level4Dir.resolve("deep-agent.jsonl");
      Files.writeString(level4Session, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(3);
      assertThat(sessions).containsExactlyInAnyOrder(directSession, level2Session, level4Session);
    }

    @Test
    @DisplayName("跳过嵌套隐藏目录中的会话文件")
    void skipsNestedHiddenDirectories() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      Path normalSession = projectDir.resolve("visible.jsonl");
      Files.writeString(normalSession, "{}\n", StandardCharsets.UTF_8);

      // 隐藏目录中的会话不应被发现
      Path hiddenDir = projectDir.resolve("session-001").resolve(".hidden");
      Files.createDirectories(hiddenDir);
      Path hiddenSession = hiddenDir.resolve("secret.jsonl");
      Files.writeString(hiddenSession, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(normalSession);
    }

    @Test
    @DisplayName("嵌套会话按完整路径确定性排序")
    void nestedSessionsSortedByFullPath() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      Path zSession = projectDir.resolve("z-root.jsonl");
      Files.writeString(zSession, "{}\n", StandardCharsets.UTF_8);

      Path aSubDir = projectDir.resolve("aaa").resolve("subagents");
      Files.createDirectories(aSubDir);
      Path aNested = aSubDir.resolve("agent.jsonl");
      Files.writeString(aNested, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }

    @Test
    @DisplayName("空子目录不影响发现结果")
    void emptySubdirectoriesDoNotAffectResults() throws IOException {
      Path projects = tempDir.resolve("projects");
      Path projectDir = projects.resolve("my-project");
      Files.createDirectories(projectDir);

      Path sessionFile = projectDir.resolve("session.jsonl");
      Files.writeString(sessionFile, "{}\n", StandardCharsets.UTF_8);

      // 创建多个空子目录
      Files.createDirectories(projectDir.resolve("empty-dir-1"));
      Files.createDirectories(projectDir.resolve("empty-dir-2").resolve("nested-empty"));

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }
  }
}
