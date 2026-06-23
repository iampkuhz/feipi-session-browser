package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.artifact.normalized.ArtifactConstants;
import com.feipi.session.browser.artifact.normalized.SafeArtifactName;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link SessionDeleter} 测试。
 *
 * <p>覆盖 DB 删除顺序（先 session_artifacts，后 sessions）、更新路径、孤儿 artifact 清理。
 */
class SessionDeleterTest {

  @TempDir Path tempDir;

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    new com.feipi.session.browser.index.sqlite.IndexSchema(
            com.feipi.session.browser.index.sqlite.MigrationRunner.withAllMigrations())
        .ensureSchema(conn);
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void deleteSessionRemovesArtifactsFirst() throws SQLException {
    insertSession("claude_code:s1", "claude_code");
    insertArtifact("claude_code:s1", "raw");

    int deleted = SessionDeleter.deleteSession(conn, "claude_code:s1");

    assertThat(deleted).isEqualTo(1);
    assertThat(sessionExists("claude_code:s1")).isFalse();
    assertThat(artifactExists("claude_code:s1")).isFalse();
  }

  @Test
  void deleteNonExistentSessionReturnsZero() throws SQLException {
    int deleted = SessionDeleter.deleteSession(conn, "nonexistent");
    assertThat(deleted).isZero();
  }

  @Test
  void updateSessionPathChangesFilePath() throws SQLException {
    insertSession("claude_code:s1", "claude_code");

    int updated =
        SessionDeleter.updateSessionPath(conn, "claude_code:s1", "/new/path.jsonl", 123.456);

    assertThat(updated).isEqualTo(1);
    assertThat(getFilePath("claude_code:s1")).isEqualTo("/new/path.jsonl");
    assertThat(getFileMtime("claude_code:s1"))
        .isCloseTo(123.456, org.assertj.core.data.Offset.offset(0.001));
  }

  @Test
  void updateNonExistentSessionReturnsZero() throws SQLException {
    int updated = SessionDeleter.updateSessionPath(conn, "nonexistent", "/new/path.jsonl", 0);
    assertThat(updated).isZero();
  }

  @Test
  void deleteOrphanArtifactsRemovesFilesWithoutDBRows() throws Exception {
    Path artifactDir = tempDir.resolve("artifacts");
    Files.createDirectories(artifactDir);

    // 创建两个 artifact 文件
    Path orphanData = artifactDir.resolve("orphan-session" + ArtifactConstants.DATA_FILE_SUFFIX);
    Path orphanMeta = artifactDir.resolve("orphan-session" + ArtifactConstants.META_FILE_SUFFIX);
    Files.writeString(orphanData, "{}");
    Files.writeString(orphanMeta, "{}");

    // validSessionKeys 不包含 orphan-session 对应的 key
    Set<String> validKeys = new HashSet<>();
    validKeys.add("claude_code:surviving");

    List<String> errors = new ArrayList<>();
    int orphanCount = SessionDeleter.deleteOrphanArtifacts(artifactDir, validKeys, errors);

    // orphanData 的 safe name 不匹配任何 validKeys，所以被删除
    assertThat(orphanCount).isEqualTo(1);
    assertThat(Files.exists(orphanData)).isFalse();
    assertThat(Files.exists(orphanMeta)).isFalse();
  }

  @Test
  void deleteOrphanArtifactsKeepsValidArtifacts() throws Exception {
    Path artifactDir = tempDir.resolve("valid-artifacts");
    Files.createDirectories(artifactDir);

    // 创建 artifact 文件，其 safe name 对应 validKeys 中的一个
    String sessionKey = "claude_code:valid-session";
    String safeName = SafeArtifactName.sanitize(sessionKey);
    Path dataFile = artifactDir.resolve(safeName + ArtifactConstants.DATA_FILE_SUFFIX);
    Files.writeString(dataFile, "{}");

    Set<String> validKeys = new HashSet<>();
    validKeys.add(sessionKey);

    List<String> errors = new ArrayList<>();
    int orphanCount = SessionDeleter.deleteOrphanArtifacts(artifactDir, validKeys, errors);

    assertThat(orphanCount).isZero();
    assertThat(Files.exists(dataFile)).isTrue();
  }

  @Test
  void deleteOrphanArtifactsSkipsNonExistentDirectory() {
    Path nonExistent = tempDir.resolve("does-not-exist");

    List<String> errors = new ArrayList<>();
    int orphanCount = SessionDeleter.deleteOrphanArtifacts(nonExistent, Set.of(), errors);

    assertThat(orphanCount).isZero();
    assertThat(errors).isEmpty();
  }

  @Test
  void deleteOrphanArtifactsIgnoresTempFiles() throws Exception {
    Path artifactDir = tempDir.resolve("temp-artifacts");
    Files.createDirectories(artifactDir);

    // 创建临时文件（不应该被当作孤儿 artifact）
    Path tempFile = artifactDir.resolve(ArtifactConstants.TEMP_FILE_PREFIX + "some-uuid");
    Files.writeString(tempFile, "temp");

    List<String> errors = new ArrayList<>();
    int orphanCount = SessionDeleter.deleteOrphanArtifacts(artifactDir, Set.of(), errors);

    assertThat(orphanCount).isZero();
    assertThat(Files.exists(tempFile)).isTrue();
  }

  // ===== 辅助方法 =====

  private void insertSession(String sessionKey, String agent) throws SQLException {
    String sql =
        "INSERT INTO sessions (session_key, agent, session_id, title, project_key, "
            + "ended_at, file_mtime, file_path) VALUES (?, ?, ?, '', ?, '2025-01-01T00:00:00Z', 0, '')";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      stmt.setString(2, agent);
      String sessionId =
          sessionKey.contains(":") ? sessionKey.substring(sessionKey.indexOf(':') + 1) : sessionKey;
      stmt.setString(3, sessionId);
      stmt.setString(4, "proj");
      stmt.executeUpdate();
    }
  }

  private void insertArtifact(String sessionKey, String artifactType) throws SQLException {
    String sql =
        "INSERT INTO session_artifacts (session_key, artifact_type, path) VALUES (?, ?, ?)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      stmt.setString(2, artifactType);
      stmt.setString(3, "/some/path");
      stmt.executeUpdate();
    }
  }

  private boolean sessionExists(String sessionKey) throws SQLException {
    String sql = "SELECT COUNT(*) FROM sessions WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      try (ResultSet rs = stmt.executeQuery()) {
        return rs.next() && rs.getInt(1) > 0;
      }
    }
  }

  private boolean artifactExists(String sessionKey) throws SQLException {
    String sql = "SELECT COUNT(*) FROM session_artifacts WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      try (ResultSet rs = stmt.executeQuery()) {
        return rs.next() && rs.getInt(1) > 0;
      }
    }
  }

  private String getFilePath(String sessionKey) throws SQLException {
    String sql = "SELECT file_path FROM sessions WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
          return rs.getString("file_path");
        }
      }
    }
    return null;
  }

  private double getFileMtime(String sessionKey) throws SQLException {
    String sql = "SELECT file_mtime FROM sessions WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
          return rs.getDouble("file_mtime");
        }
      }
    }
    return 0.0;
  }
}
