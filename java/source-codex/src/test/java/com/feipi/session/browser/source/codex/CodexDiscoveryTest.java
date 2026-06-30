package com.feipi.session.browser.source.codex;

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
 * {@link CodexDiscovery} 单元测试。
 *
 * <p>验证会话发现逻辑在各种目录结构下的行为：sessions/ 年/月/日三层结构、 archived_sessions/
 * 扁平结构、隐藏文件过滤、空目录和边界场景。
 */
@DisplayName("CodexDiscovery 会话发现测试")
class CodexDiscoveryTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("空目录和边界场景")
  class EmptyAndBoundary {

    @Test
    @DisplayName("空目录返回空列表")
    void emptyDirectoryReturnsEmptyList() {
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("null 路径返回空列表")
    void nullPathReturnsEmptyList() {
      List<Path> sessions = CodexDiscovery.discoverSessions(null);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("sessions/ 目录不存在时返回空列表")
    void noSessionsDirReturnsEmptyList() throws IOException {
      // 只有无关文件，没有 sessions/ 或 archived_sessions/
      Files.writeString(tempDir.resolve("somefile.txt"), "hello", StandardCharsets.UTF_8);
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("sessions/ 存在但为空目录时返回空列表")
    void emptySessionsDirReturnsEmptyList() throws IOException {
      Files.createDirectory(tempDir.resolve(CodexConstants.SESSIONS_DIR));
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("跳过根目录下的非 jsonl 文件")
    void skipNonJsonlFilesInRoot() throws IOException {
      Files.createDirectory(tempDir.resolve(CodexConstants.SESSIONS_DIR));
      // 根目录下的 session_index.jsonl 不应被发现（不在 sessions/ 或 archived_sessions/ 下）
      Files.writeString(tempDir.resolve("session_index.jsonl"), "{}\n", StandardCharsets.UTF_8);
      Files.writeString(tempDir.resolve("history.jsonl"), "{}\n", StandardCharsets.UTF_8);
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }
  }

  @Nested
  @DisplayName("sessions/ 目录发现")
  class SessionsDirDiscovery {

    @Test
    @DisplayName("单日期单 rollout 发现")
    void singleRolloutDiscovered() throws IOException {
      Path dayDir =
          tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("12");
      Files.createDirectories(dayDir);
      Path rollout = dayDir.resolve("rollout-20260612-abc-123.jsonl");
      Files.writeString(rollout, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }

    @Test
    @DisplayName("多日期多 rollout 按路径确定性排序")
    void multipleDatesMultipleRolloutsSorted() throws IOException {
      // 2026/06/12 有两个 rollout
      Path day12 =
          tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("12");
      Files.createDirectories(day12);
      Path rollout1 = day12.resolve("rollout-100-aaa.jsonl");
      Path rollout2 = day12.resolve("rollout-200-bbb.jsonl");
      Files.writeString(rollout1, "{}\n", StandardCharsets.UTF_8);
      Files.writeString(rollout2, "{}\n", StandardCharsets.UTF_8);

      // 2026/06/13 有一个 rollout
      Path day13 =
          tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("13");
      Files.createDirectories(day13);
      Path rollout3 = day13.resolve("rollout-100-ccc.jsonl");
      Files.writeString(rollout3, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(3);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }

    @Test
    @DisplayName("跳过 sessions/ 下的隐藏目录")
    void skipHiddenDirsInSessions() throws IOException {
      Path sessionsDir = tempDir.resolve(CodexConstants.SESSIONS_DIR);
      Path hiddenDir = sessionsDir.resolve(".tmp");
      Files.createDirectories(hiddenDir);
      Files.writeString(
          hiddenDir.resolve("temp.jsonl"), "{}\n", StandardCharsets.UTF_8);

      // 正常日期目录
      Path dayDir = sessionsDir.resolve("2026").resolve("06").resolve("12");
      Files.createDirectories(dayDir);
      Path rollout = dayDir.resolve("rollout-100-aaa.jsonl");
      Files.writeString(rollout, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }
  }

  @Nested
  @DisplayName("archived_sessions/ 目录发现")
  class ArchivedDirDiscovery {

    @Test
    @DisplayName("扁平结构 rollout 发现")
    void flatArchivedRolloutDiscovered() throws IOException {
      Path archivedDir = tempDir.resolve(CodexConstants.ARCHIVED_SESSION_DIR);
      Files.createDirectories(archivedDir);
      Path rollout = archivedDir.resolve("rollout-20260101-old-uuid.jsonl");
      Files.writeString(rollout, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }

    @Test
    @DisplayName("跳过 archived_sessions/ 下的隐藏文件")
    void skipHiddenFilesInArchived() throws IOException {
      Path archivedDir = tempDir.resolve(CodexConstants.ARCHIVED_SESSION_DIR);
      Files.createDirectories(archivedDir);

      Path hiddenFile = archivedDir.resolve(".hidden-rollout.jsonl");
      Files.writeString(hiddenFile, "{}\n", StandardCharsets.UTF_8);

      Path normalRollout = archivedDir.resolve("rollout-20260101-aaa.jsonl");
      Files.writeString(normalRollout, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(normalRollout);
    }
  }

  @Nested
  @DisplayName("组合场景")
  class Combined {

    @Test
    @DisplayName("同时发现 sessions/ 和 archived_sessions/ 中的文件")
    void bothDirectoriesDiscovered() throws IOException {
      // 活跃会话目录下的 rollout 文件：sessions/2026/06/12/
      Path dayDir =
          tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("12");
      Files.createDirectories(dayDir);
      Path activeRollout = dayDir.resolve("rollout-20260612-aaa.jsonl");
      Files.writeString(activeRollout, "{}\n", StandardCharsets.UTF_8);

      // 归档会话目录下的 rollout 文件
      Path archivedDir = tempDir.resolve(CodexConstants.ARCHIVED_SESSION_DIR);
      Files.createDirectories(archivedDir);
      Path archivedRollout = archivedDir.resolve("rollout-20260101-bbb.jsonl");
      Files.writeString(archivedRollout, "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }
  }
}
