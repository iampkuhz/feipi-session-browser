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
 * <p>验证基于 history.jsonl 的会话发现逻辑： 去重、transcript 定位、缺失 transcript 处理、确定性排序。
 */
@DisplayName("ClaudeDiscovery 会话发现测试")
class ClaudeDiscoveryTest {

  @TempDir Path tempDir;

  /** 写入 history.jsonl 文件。 */
  private void writeHistory(String... lines) throws IOException {
    Files.writeString(
        tempDir.resolve(ClaudeConstants.HISTORY_FILE),
        String.join("\n", lines) + "\n",
        StandardCharsets.UTF_8);
  }

  /** 在 {@code projects/<project>/} 下创建 transcript 文件。 */
  private Path createTranscript(String project, String sessionId) throws IOException {
    Path projectDir = tempDir.resolve(ClaudeConstants.PROJECTS_DIR).resolve(project);
    Files.createDirectories(projectDir);
    Path transcript = projectDir.resolve(sessionId + ".jsonl");
    Files.writeString(transcript, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);
    return transcript;
  }

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
    @DisplayName("无 history.jsonl 返回空列表")
    void noHistoryFileReturnsEmptyList() throws IOException {
      Files.createDirectory(tempDir.resolve("projects"));
      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }
  }

  @Nested
  @DisplayName("正常会话发现")
  class NormalDiscovery {

    @Test
    @DisplayName("单项目单会话发现")
    void singleProjectSingleSession() throws IOException {
      writeHistory(
          "{\"sessionId\":\"session-001\",\"project\":\"my-project\",\"display\":\"Test\",\"timestamp\":1000}");
      Path transcript = createTranscript("my-project", "session-001");

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(transcript);
    }

    @Test
    @DisplayName("多项目多会话按 sessionId 确定性排序")
    void multipleProjectsMultipleSessionsSorted() throws IOException {
      writeHistory(
          "{\"sessionId\":\"beta-id\",\"project\":\"project-b\",\"display\":\"B\",\"timestamp\":2000}",
          "{\"sessionId\":\"alpha-id\",\"project\":\"project-a\",\"display\":\"A\",\"timestamp\":1000}");
      createTranscript("project-b", "beta-id");
      createTranscript("project-a", "alpha-id");

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      // 按 sessionId 排序：alpha-id < beta-id
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }
  }

  @Nested
  @DisplayName("去重和缺失 transcript")
  class DeduplicationAndMissingTranscript {

    @Test
    @DisplayName("同一 sessionId 去重保留最后一条")
    void deduplicatesBySessionId() throws IOException {
      writeHistory(
          "{\"sessionId\":\"dup-id\",\"project\":\"old-project\",\"display\":\"Old\",\"timestamp\":1000}",
          "{\"sessionId\":\"dup-id\",\"project\":\"new-project\",\"display\":\"New\",\"timestamp\":2000}");
      Path transcript = createTranscript("new-project", "dup-id");

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(transcript);
    }

    @Test
    @DisplayName("transcript 缺失时仍返回合成路径")
    void missingTranscriptReturnsSyntheticPath() throws IOException {
      writeHistory(
          "{\"sessionId\":\"missing-id\",\"project\":\"some-project\",\"display\":\"Test\",\"timestamp\":1000}");
      // 不创建 transcript 文件

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      // 路径应为 projects/some-project/missing-id.jsonl（合成路径）
      Path expected =
          tempDir
              .resolve(ClaudeConstants.PROJECTS_DIR)
              .resolve("some-project")
              .resolve("missing-id.jsonl");
      assertThat(sessions.get(0)).isEqualTo(expected);
      assertThat(Files.exists(expected)).isFalse();
    }
  }

  @Nested
  @DisplayName("transcript 定位策略")
  class TranscriptLocation {

    @Test
    @DisplayName("优先在记录的项目目录下查找 transcript")
    void prefersRecordedProjectDir() throws IOException {
      writeHistory(
          "{\"sessionId\":\"sess-1\",\"project\":\"correct-project\",\"display\":\"Test\",\"timestamp\":1000}");
      Path correctTranscript = createTranscript("correct-project", "sess-1");
      // 在另一个项目目录也创建同名文件
      createTranscript("other-project", "sess-1");

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(correctTranscript);
    }

    @Test
    @DisplayName("记录的项目目录无文件时搜索其他项目目录")
    void searchesOtherProjectDirsWhenRecordedDirMissing() throws IOException {
      writeHistory(
          "{\"sessionId\":\"sess-1\",\"project\":\"wrong-project\",\"display\":\"Test\",\"timestamp\":1000}");
      // 不在 wrong-project 下创建文件，在 actual-project 下创建
      Path actualTranscript = createTranscript("actual-project", "sess-1");

      List<Path> sessions = ClaudeDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(actualTranscript);
    }
  }
}
