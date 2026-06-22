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
 * <p>验证会话发现逻辑在各种目录结构下的行为：空目录、 日期目录/会话目录结构、多日期多会话排序、隐藏文件过滤。
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
    @DisplayName("无 day 子目录返回空列表")
    void noDaySubdirReturnsEmptyList() throws IOException {
      // 创建文件而不是目录
      Files.writeString(tempDir.resolve("somefile.txt"), "hello", StandardCharsets.UTF_8);
      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);
      assertThat(sessions).isEmpty();
    }
  }

  @Nested
  @DisplayName("正常会话发现")
  class NormalDiscovery {

    @Test
    @DisplayName("单 day 单 session 发现")
    void singleDaySingleSession() throws IOException {
      Path dayDir = tempDir.resolve("2024-01-15");
      Path sessionDir = dayDir.resolve("session-001");
      Files.createDirectories(sessionDir);
      Path sessionFile = sessionDir.resolve("session.jsonl");
      Files.writeString(sessionFile, "{\"type\":\"assistant\"}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }

    @Test
    @DisplayName("多 day 多 session 按路径确定性排序")
    void multipleDaysMultipleSessionsSorted() throws IOException {
      // day-b 有 session-beta 和 session-alpha
      Path dayB = tempDir.resolve("2024-02-01");
      Path sessionBeta = dayB.resolve("session-beta");
      Path sessionAlpha = dayB.resolve("session-alpha");
      Files.createDirectories(sessionBeta);
      Files.createDirectories(sessionAlpha);
      Files.writeString(sessionBeta.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);
      Files.writeString(sessionAlpha.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);

      // day-a 有 session-second 和 session-first
      Path dayA = tempDir.resolve("2024-01-15");
      Path sessionSecond = dayA.resolve("session-second");
      Path sessionFirst = dayA.resolve("session-first");
      Files.createDirectories(sessionSecond);
      Files.createDirectories(sessionFirst);
      Files.writeString(sessionSecond.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);
      Files.writeString(sessionFirst.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(4);
      List<String> sessionStrs = sessions.stream().map(Path::toString).toList();
      assertThat(sessionStrs).isSorted();
    }
  }

  @Nested
  @DisplayName("文件和目录过滤")
  class Filtering {

    @Test
    @DisplayName("跳过缺少 session.jsonl 的目录")
    void skipDirsWithoutSessionFile() throws IOException {
      Path dayDir = tempDir.resolve("2024-01-15");

      // 有 session.jsonl 的 session 目录
      Path validSession = dayDir.resolve("valid-session");
      Files.createDirectories(validSession);
      Path sessionFile = validSession.resolve("session.jsonl");
      Files.writeString(sessionFile, "{}\n", StandardCharsets.UTF_8);

      // 没有 session.jsonl 的 session 目录
      Path emptySession = dayDir.resolve("empty-session");
      Files.createDirectories(emptySession);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(sessionFile);
    }

    @Test
    @DisplayName("跳过隐藏文件和隐藏目录")
    void skipHiddenFilesAndDirectories() throws IOException {
      // 隐藏日期目录
      Path hiddenDay = tempDir.resolve(".hidden-day");
      Files.createDirectories(hiddenDay);
      Path hiddenSession = hiddenDay.resolve("session-001");
      Files.createDirectories(hiddenSession);
      Files.writeString(hiddenSession.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);

      // 正常日期目录
      Path normalDay = tempDir.resolve("2024-01-15");
      Path normalSession = normalDay.resolve("session-001");
      Files.createDirectories(normalSession);
      Path normalFile = normalSession.resolve("session.jsonl");
      Files.writeString(normalFile, "{}\n", StandardCharsets.UTF_8);

      // 正常日期下的隐藏 session 目录
      Path hiddenSessionDir = normalDay.resolve(".hidden-session");
      Files.createDirectories(hiddenSessionDir);
      Files.writeString(hiddenSessionDir.resolve("session.jsonl"), "{}\n", StandardCharsets.UTF_8);

      List<Path> sessions = CodexDiscovery.discoverSessions(tempDir);

      assertThat(sessions).hasSize(1);
      assertThat(sessions.get(0)).isEqualTo(normalFile);
    }
  }
}
