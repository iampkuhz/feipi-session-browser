package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link RepairEngine} 集成测试。
 *
 * <p>覆盖 repair 状态机全部路径：确认删除、根目录不可用、临时缺失、重命名检测和无操作。 验证幂等性、删除顺序和孤儿 artifact 清理。
 */
class RepairEngineTest {

  @TempDir Path tempDir;

  private Connection conn;
  private RepairEngine engine;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    new com.feipi.session.browser.index.sqlite.IndexSchema(
            com.feipi.session.browser.index.sqlite.MigrationRunner.withAllMigrations())
        .ensureSchema(conn);
    engine = new RepairEngine();
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void emptyDatabaseProducesNoDecisions() {
    Path root = tempDir.resolve("empty-root");
    safeCreateDirectories(root);

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    List<RepairDecision> decisions = engine.analyze(conn, entries);
    assertThat(decisions).isEmpty();
  }

  @Test
  void existingSourceFileProducesNoAction() throws Exception {
    // 创建源文件
    Path root = tempDir.resolve("source-root");
    Path sourceFile = root.resolve("session-1.jsonl");
    safeCreateDirectories(root);
    Files.writeString(sourceFile, "{\"test\": true}");

    // 在 sessions 表中插入记录
    insertSession("claude_code:session-1", sourceFile.toString(), "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    List<RepairDecision> decisions = engine.analyze(conn, entries);

    assertThat(decisions).hasSize(1);
    assertThat(decisions.get(0).action()).isEqualTo(RepairAction.NO_ACTION);
    assertThat(decisions.get(0).fingerprint().sessionKey()).isEqualTo("claude_code:session-1");
  }

  @Test
  void missingSourceFileProducesConfirmedDelete() throws Exception {
    Path root = tempDir.resolve("delete-root");
    safeCreateDirectories(root);

    // 插入记录，源文件不存在
    insertSession("claude_code:session-deleted", "/nonexistent/path.jsonl", "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    List<RepairDecision> decisions = engine.analyze(conn, entries);

    assertThat(decisions).hasSize(1);
    assertThat(decisions.get(0).action()).isEqualTo(RepairAction.CONFIRMED_DELETE);
  }

  @Test
  void unavailableRootProducesRootUnavailable() throws Exception {
    // 根目录不存在
    Path nonExistent = tempDir.resolve("non-existent-root");

    insertSession("claude_code:session-1", "/some/path.jsonl", "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), nonExistent));

    List<RepairDecision> decisions = engine.analyze(conn, entries);

    assertThat(decisions).hasSize(1);
    assertThat(decisions.get(0).action()).isEqualTo(RepairAction.ROOT_UNAVAILABLE);
  }

  @Test
  void renameDetectedWhenFileMoved() throws Exception {
    Path root = tempDir.resolve("rename-root");
    Path projectDir = root.resolve("project-A");
    safeCreateDirectories(projectDir);

    // 源文件在新位置
    Path newFile = projectDir.resolve("moved-session.jsonl");
    Files.writeString(newFile, "{\"moved\": true}");

    // 插入记录，路径指向旧位置
    insertSession("claude_code:moved-session", "/old/path/moved-session.jsonl", "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    List<RepairDecision> decisions = engine.analyze(conn, entries);

    assertThat(decisions).hasSize(1);
    assertThat(decisions.get(0).action()).isEqualTo(RepairAction.RENAME_DETECTED);
    assertThat(decisions.get(0).newFilePath()).isPresent();
    assertThat(decisions.get(0).newFilePath().get()).contains("moved-session");
  }

  @Test
  void executeConfirmedDeleteRemovesDBRows() throws Exception {
    Path root = tempDir.resolve("execute-delete");
    safeCreateDirectories(root);

    insertSession("claude_code:to-delete", "/nonexistent/path.jsonl", "claude_code");
    insertArtifact("claude_code:to-delete", "raw");

    List<RepairDecision> decisions =
        List.of(
            RepairDecision.confirmedDelete(
                new StoredSessionFingerprint(
                    "claude_code:to-delete", "/nonexistent/path.jsonl", 0, "claude_code", ""),
                "源文件不存在"));

    RepairSummary summary = engine.execute(conn, decisions, tempDir.resolve("artifacts"));

    assertThat(summary.deletedCount()).isEqualTo(1);
    assertThat(sessionExists("claude_code:to-delete")).isFalse();
    assertThat(artifactExists("claude_code:to-delete")).isFalse();
  }

  @Test
  void executeRenameUpdatesPath() throws Exception {
    Path root = tempDir.resolve("execute-rename");
    Path projectDir = root.resolve("project-A");
    safeCreateDirectories(projectDir);

    Path newFile = projectDir.resolve("renamed-session.jsonl");
    Files.writeString(newFile, "{\"data\": true}");

    insertSession("claude_code:renamed-session", "/old/path.jsonl", "claude_code");

    StoredSessionFingerprint fp =
        new StoredSessionFingerprint(
            "claude_code:renamed-session", "/old/path.jsonl", 0, "claude_code", "");

    List<RepairDecision> decisions = List.of(RepairDecision.renameDetected(fp, newFile.toString()));

    RepairSummary summary = engine.execute(conn, decisions, tempDir.resolve("artifacts"));

    assertThat(summary.renamedCount()).isEqualTo(1);
    assertThat(getSessionFilePath("claude_code:renamed-session")).isEqualTo(newFile.toString());
  }

  @Test
  void repairIsIdempotent() throws Exception {
    Path root = tempDir.resolve("idempotent-root");
    safeCreateDirectories(root);

    insertSession("claude_code:to-delete", "/nonexistent/path.jsonl", "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    // 第一次 repair
    RepairSummary first = engine.repair(conn, entries, tempDir.resolve("artifacts"));
    assertThat(first.deletedCount()).isEqualTo(1);

    // 第二次 repair — 幂等，不再有删除动作
    RepairSummary second = engine.repair(conn, entries, tempDir.resolve("artifacts"));
    assertThat(second.deletedCount()).isZero();
    assertThat(second.keptCount()).isZero();
  }

  @Test
  void temporaryRootUnavailableDoesNotDelete() throws Exception {
    // 根目录不存在 → ROOT_UNAVAILABLE → 不删除
    Path nonExistent = tempDir.resolve("non-existent");

    insertSession("claude_code:session-1", "/some/path.jsonl", "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), nonExistent));

    RepairSummary summary = engine.repair(conn, entries, tempDir.resolve("artifacts"));

    assertThat(summary.deletedCount()).isZero();
    assertThat(summary.rootUnavailableCount()).isEqualTo(1);
    // DB 行仍然存在
    assertThat(sessionExists("claude_code:session-1")).isTrue();
  }

  @Test
  void missingAgentProducesTemporaryMissing() throws Exception {
    Path root = tempDir.resolve("unknown-agent-root");
    safeCreateDirectories(root);

    // 插入一个 agent 为 qoder 的会话，但只配置 claude_code 源
    insertSession("qoder:session-1", "/some/path.jsonl", "qoder");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    List<RepairDecision> decisions = engine.analyze(conn, entries);

    assertThat(decisions).hasSize(1);
    assertThat(decisions.get(0).action()).isEqualTo(RepairAction.SOURCE_MISSING_TEMPORARY);
  }

  @Test
  void orphanArtifactDeletion() throws Exception {
    Path artifactDir = tempDir.resolve("orphan-artifacts");
    safeCreateDirectories(artifactDir);

    // 创建孤儿 artifact 文件
    com.feipi.session.browser.artifact.normalized.SafeArtifactName safe = null;
    String safeName;
    try {
      safeName =
          com.feipi.session.browser.artifact.normalized.SafeArtifactName.sanitize(
              "claude_code:orphan-session");
    } catch (Exception e) {
      safeName = "claude_code_orphan-session";
    }

    Path dataFile = artifactDir.resolve(safeName + ".json");
    Path metaFile = artifactDir.resolve(safeName + ".meta.json");
    Files.writeString(dataFile, "{\"orphan\": true}");
    Files.writeString(metaFile, "{\"meta\": true}");

    // DB 中没有对应 session
    List<RepairDecision> decisions = List.of();

    RepairSummary summary = engine.execute(conn, decisions, artifactDir);

    assertThat(summary.artifactOrphanCount()).isEqualTo(1);
    assertThat(Files.exists(dataFile)).isFalse();
    assertThat(Files.exists(metaFile)).isFalse();
  }

  @Test
  void repairSummaryCountsAreConsistent() throws Exception {
    Path root = tempDir.resolve("counts-root");
    safeCreateDirectories(root);

    // 创建源文件
    Path existingFile = root.resolve("existing-session.jsonl");
    Files.writeString(existingFile, "{\"data\": true}");

    // 已存在的会话
    insertSession("claude_code:existing-session", existingFile.toString(), "claude_code");
    // 不存在的会话
    insertSession("claude_code:deleted-session", "/nonexistent/path.jsonl", "claude_code");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    RepairSummary summary = engine.repair(conn, entries, tempDir.resolve("artifacts"));

    assertThat(summary.keptCount()).isEqualTo(1);
    assertThat(summary.deletedCount()).isEqualTo(1);
    assertThat(summary.totalActions()).isEqualTo(1);
    assertThat(summary.hasDestructiveActions()).isTrue();
  }

  @Test
  void deleteOrderArtifactsBeforeSessions() throws Exception {
    Path root = tempDir.resolve("delete-order");
    safeCreateDirectories(root);

    insertSession("claude_code:to-delete", "/nonexistent/path.jsonl", "claude_code");
    insertArtifact("claude_code:to-delete", "raw");

    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    RepairSummary summary = engine.repair(conn, entries, tempDir.resolve("artifacts"));

    assertThat(summary.deletedCount()).isEqualTo(1);
    assertThat(summary.hasErrors()).isFalse();
    // 两个表的数据都已删除
    assertThat(sessionExists("claude_code:to-delete")).isFalse();
    assertThat(artifactExists("claude_code:to-delete")).isFalse();
  }

  @Test
  void noAgentMatchProducesEmptyDecisions() {
    Path root = tempDir.resolve("no-agent");
    safeCreateDirectories(root);

    // 没有已索引会话
    List<ScanConfig.SourceEntry> entries =
        List.of(new ScanConfig.SourceEntry(new NoopAdapter(SourceId.CLAUDE_CODE), root));

    List<RepairDecision> decisions = engine.analyze(conn, entries);
    assertThat(decisions).isEmpty();
  }

  @Test
  void repairSummaryValidationRejectsNegativeCounts() {
    assertThatThrownBy(() -> new RepairSummary(-1, 0, 0, 0, 0, 0, List.of(), List.of(), 0))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void repairSummaryHasErrorsReflectsErrorList() {
    RepairSummary withErrors =
        new RepairSummary(0, 0, 0, 0, 0, 0, List.of(), List.of("error"), 100);
    assertThat(withErrors.hasErrors()).isTrue();

    RepairSummary noErrors = new RepairSummary(0, 0, 0, 0, 0, 0, List.of(), List.of(), 100);
    assertThat(noErrors.hasErrors()).isFalse();
  }

  // ===== 辅助方法 =====

  /** 在 sessions 表中插入一条已索引会话记录。 */
  private void insertSession(String sessionKey, String filePath, String agent) throws SQLException {
    String sql =
        "INSERT INTO sessions (session_key, agent, session_id, title, project_key, "
            + "ended_at, file_mtime, file_path) VALUES (?, ?, ?, '', ?, '2025-01-01T00:00:00Z', 0, ?)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      stmt.setString(2, agent);
      String sessionId =
          sessionKey.contains(":") ? sessionKey.substring(sessionKey.indexOf(':') + 1) : sessionKey;
      stmt.setString(3, sessionId);
      stmt.setString(4, "proj");
      stmt.setString(5, filePath);
      stmt.executeUpdate();
    }
  }

  /** 在 session_artifacts 表中插入一条关联记录。 */
  private void insertArtifact(String sessionKey, String artifactType) throws SQLException {
    String sql =
        "INSERT INTO session_artifacts (session_key, artifact_type, path) VALUES (?, ?, ?)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      stmt.setString(2, artifactType);
      stmt.setString(3, "/some/artifact/path");
      stmt.executeUpdate();
    }
  }

  /** 检查 sessions 表中是否存在指定 session key。 */
  private boolean sessionExists(String sessionKey) throws SQLException {
    String sql = "SELECT COUNT(*) FROM sessions WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      try (ResultSet rs = stmt.executeQuery()) {
        return rs.next() && rs.getInt(1) > 0;
      }
    }
  }

  /** 检查 session_artifacts 表中是否存在指定 session key 的记录。 */
  private boolean artifactExists(String sessionKey) throws SQLException {
    String sql = "SELECT COUNT(*) FROM session_artifacts WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      try (ResultSet rs = stmt.executeQuery()) {
        return rs.next() && rs.getInt(1) > 0;
      }
    }
  }

  /** 获取 sessions 表中指定 session key 的 file_path。 */
  private String getSessionFilePath(String sessionKey) throws SQLException {
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

  /** 创建目录，忽略异常。 */
  private void safeCreateDirectories(Path dir) {
    try {
      Files.createDirectories(dir);
    } catch (Exception e) {
      // 忽略
    }
  }

  // ===== 测试用适配器 =====

  /** 不做任何实际工作的适配器。 */
  private static class NoopAdapter implements SourceAdapter {
    private final SourceId sourceId;

    NoopAdapter(SourceId sourceId) {
      this.sourceId = sourceId;
    }

    @Override
    public SourceId sourceId() {
      return sourceId;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          List.of(), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), sourceId, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 0, List.of(), null, null);
    }
  }
}
