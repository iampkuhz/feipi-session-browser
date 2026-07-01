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
 * <p>验证基于 session_index.jsonl + state_5.sqlite 的会话发现逻辑： session_index.jsonl 回退发现、
 * rollout 文件定位、transcript 缺失处理、确定性排序。
 *
 * <p>注意：这些测试不创建真实的 SQLite 数据库，仅验证 session_index.jsonl 驱动的发现路径。
 */
@DisplayName("CodexDiscovery 会话发现测试")
class CodexDiscoveryTest {

  @TempDir Path tempDir;

  /** 写入 session_index.jsonl 文件。 */
  private void writeSessionIndex(String... lines) throws IOException {
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        String.join("\n", lines) + "\n",
        StandardCharsets.UTF_8);
  }

  /** 在 sessions/<year>/<month>/<day>/ 下创建 rollout 文件。 */
  private Path createRollout(String year, String month, String day, String filename)
      throws IOException {
    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve(year).resolve(month).resolve(day);
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve(filename);
    Files.writeString(rollout, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);
    return rollout;
  }

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
    @DisplayName("无 session_index.jsonl 且无 threads.db 返回空列表")
    void noIndexOrThreadsReturnsEmptyList() throws IOException {
      Files.createDirectory(tempDir.resolve(CodexConstants.SESSIONS_DIR));
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }

    @Test
    @DisplayName("session_index.jsonl 为空时返回空列表")
    void emptySessionIndexReturnsEmptyList() throws IOException {
      writeSessionIndex();
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }
  }

  @Nested
  @DisplayName("session_index.jsonl 驱动发现")
  class SessionIndexDiscovery {

    @Test
    @DisplayName("单条 session_index 条目发现 rollout")
    void singleRolloutDiscovered() throws IOException {
      writeSessionIndex(
          "{\"id\":\"aaa-123\",\"thread_name\":\"Test Session\",\"updated_at\":\"2026-06-12\"}");
      Path rollout = createRollout("2026", "06", "12", "rollout-100-aaa-123.jsonl");

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }

    @Test
    @DisplayName("多条 session_index 条目按 sessionId 排序")
    void multipleSessionsSorted() throws IOException {
      writeSessionIndex(
          "{\"id\":\"bbb-456\",\"thread_name\":\"Session B\",\"updated_at\":\"2026-06-13\"}",
          "{\"id\":\"aaa-123\",\"thread_name\":\"Session A\",\"updated_at\":\"2026-06-12\"}");
      createRollout("2026", "06", "12", "rollout-100-aaa-123.jsonl");
      createRollout("2026", "06", "13", "rollout-200-bbb-456.jsonl");

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(2);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }

    @Test
    @DisplayName("transcript 缺失时返回合成路径")
    void missingRolloutReturnsSyntheticPath() throws IOException {
      writeSessionIndex(
          "{\"id\":\"missing-id\",\"thread_name\":\"Missing\",\"updated_at\":\"2026-06-12\"}");
      // 不创建 rollout 文件

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      // 合成路径存在但不实际存在
      assertThat(Files.exists(sessions.get(0))).isFalse();
    }
  }

  @Nested
  @DisplayName("sessions/ 目录回退搜索")
  class SessionsDirFallback {

    @Test
    @DisplayName("session_index 条目无 rollout 时在 sessions/ 目录中搜索")
    void findsRolloutInSessionsDir() throws IOException {
      writeSessionIndex(
          "{\"id\":\"search-id\",\"thread_name\":\"Search Test\",\"updated_at\":\"2026-06-12\"}");
      // 在 sessions/ 子目录创建包含 sessionId 的 rollout 文件
      Path rollout = createRollout("2026", "06", "12", "rollout-100-search-id.jsonl");

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }

    @Test
    @DisplayName("跳过 sessions/ 下的隐藏目录")
    void skipHiddenDirsInSessions() throws IOException {
      writeSessionIndex(
          "{\"id\":\"visible-id\",\"thread_name\":\"Visible\",\"updated_at\":\"2026-06-12\"}");
      // 在隐藏目录下创建文件（不应被发现）
      Path hiddenDir = tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve(".tmp");
      Files.createDirectories(hiddenDir);
      Files.writeString(
          hiddenDir.resolve("rollout-100-hidden-id.jsonl"),
          "{}\n",
          StandardCharsets.UTF_8);
      // 在正常目录下创建文件
      Path rollout = createRollout("2026", "06", "12", "rollout-100-visible-id.jsonl");

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }
  }

  @Nested
  @DisplayName("archived_sessions/ 回退搜索")
  class ArchivedDirFallback {

    @Test
    @DisplayName("在 archived_sessions/ 中找到 rollout")
    void findsRolloutInArchivedDir() throws IOException {
      writeSessionIndex(
          "{\"id\":\"archived-id\",\"thread_name\":\"Archived\",\"updated_at\":\"2026-01-01\"}");
      // 在 archived_sessions/ 下创建 rollout
      Path archivedDir = tempDir.resolve(CodexConstants.ARCHIVED_SESSION_DIR);
      Files.createDirectories(archivedDir);
      Path rollout = archivedDir.resolve("rollout-100-archived-id.jsonl");
      Files.writeString(rollout, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }

    @Test
    @DisplayName("跳过 archived_sessions/ 下的隐藏文件")
    void skipHiddenFilesInArchived() throws IOException {
      writeSessionIndex(
          "{\"id\":\"normal-id\",\"thread_name\":\"Normal\",\"updated_at\":\"2026-01-01\"}");
      Path archivedDir = tempDir.resolve(CodexConstants.ARCHIVED_SESSION_DIR);
      Files.createDirectories(archivedDir);

      // 隐藏文件不应被发现
      Files.writeString(
          archivedDir.resolve(".hidden-rollout.jsonl"), "{}\n", StandardCharsets.UTF_8);
      // 正常 rollout
      Path rollout = archivedDir.resolve("rollout-100-normal-id.jsonl");
      Files.writeString(rollout, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(rollout);
    }
  }
}
