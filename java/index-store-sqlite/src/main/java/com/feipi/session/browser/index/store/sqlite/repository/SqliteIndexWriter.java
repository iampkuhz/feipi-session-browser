package com.feipi.session.browser.index.store.sqlite.repository;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.write.IndexWriteException;
import com.feipi.session.browser.index.api.write.IndexWriterPort;
import com.feipi.session.browser.index.api.write.MissingTranscriptSession;
import com.feipi.session.browser.index.api.write.StoredSessionFingerprint;
import com.feipi.session.browser.index.store.sqlite.mapper.ArtifactRowMapper;
import com.feipi.session.browser.index.store.sqlite.row.SessionArtifactRow;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.tx.WriteBatch;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 扫描写侧索引端口的 SQLite 实现。 */
public final class SqliteIndexWriter implements IndexWriterPort {

  private static final String SCAN_LOGIC_VERSION_KEY = "scan_logic_version";

  private static final String SESSION_INSERT_PREFIX =
      "INSERT OR REPLACE INTO sessions ("
          + "session_key, agent, session_id, title, project_key, project_name, "
          + "cwd, started_at, ended_at, duration_seconds, model_execution_seconds, "
          + "tool_execution_seconds, model, git_branch, source, "
          + "user_message_count, assistant_message_count, tool_call_count, "
          + "output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens, "
          + "total_tokens, failed_tool_count, subagent_instance_count, "
          + "indexed_at, file_mtime, file_path"
          + ") VALUES (";

  private static final String ARTIFACT_INSERT_PREFIX =
      "INSERT OR REPLACE INTO session_artifacts ("
          + "session_key, artifact_type, path, schema_version, source_path, "
          + "source_mtime, size_bytes, created_at, updated_at"
          + ") VALUES (";

  private final Connection conn;
  private final WriteBatch batch;

  public SqliteIndexWriter(Connection conn) {
    this.conn = Objects.requireNonNull(conn, "conn 不得为 null");
    this.batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
  }

  @Override
  public void ensureSchema() {
    try {
      IndexSchema.withDefaults().ensureSchema(conn);
    } catch (SQLException e) {
      throw new IndexWriteException("Schema initialization failed", e);
    }
  }

  @Override
  public void clearExistingIndex() {
    try (PreparedStatement artifacts = conn.prepareStatement("DELETE FROM session_artifacts")) {
      artifacts.executeUpdate();
      try (PreparedStatement sessions = conn.prepareStatement("DELETE FROM sessions")) {
        sessions.executeUpdate();
      }
    } catch (SQLException e) {
      throw new IndexWriteException("Clear existing index failed", e);
    }
  }

  @Override
  public long startScan(double startedAt, String mode) {
    Objects.requireNonNull(mode, "mode 不得为 null");
    String sql = "INSERT INTO scan_log (started_at, mode, status) VALUES (?, ?, 'running')";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, startedAt);
      stmt.setString(2, mode);
      stmt.executeUpdate();
      return lastInsertRowId();
    } catch (SQLException e) {
      throw new IndexWriteException("scan_log start failed", e);
    }
  }

  @Override
  public void completeScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount) {
    finishScan(scanLogId, finishedAt, perSourceCount, "success");
  }

  @Override
  public void failScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount) {
    finishScan(scanLogId, finishedAt, perSourceCount, "failure");
  }

  @Override
  public Map<String, StoredSessionFingerprint> loadStoredSessionFingerprints() {
    String sql = "SELECT session_key, file_path, file_mtime, agent, ended_at FROM sessions";
    Map<String, StoredSessionFingerprint> result = new LinkedHashMap<>();
    try (PreparedStatement stmt = conn.prepareStatement(sql);
        ResultSet rs = stmt.executeQuery()) {
      while (rs.next()) {
        String sessionKey = rs.getString("session_key");
        result.put(
            sessionKey,
            new StoredSessionFingerprint(
                sessionKey,
                rs.getString("file_path"),
                rs.getDouble("file_mtime"),
                rs.getString("agent"),
                rs.getString("ended_at")));
      }
      return Map.copyOf(result);
    } catch (SQLException e) {
      throw new IndexWriteException("Load stored fingerprints failed", e);
    }
  }

  @Override
  public int loadScanLogicVersion() {
    String sql = "SELECT value FROM index_metadata WHERE key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, SCAN_LOGIC_VERSION_KEY);
      try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
          return Integer.parseInt(rs.getString("value"));
        }
      }
    } catch (SQLException | NumberFormatException e) {
      return 0;
    }
    return 0;
  }

  @Override
  public void saveScanLogicVersion(int version, Instant updatedAt) {
    Objects.requireNonNull(updatedAt, "updatedAt 不得为 null");
    String sql = "INSERT OR REPLACE INTO index_metadata (key, value, updated_at) VALUES (?, ?, ?)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, SCAN_LOGIC_VERSION_KEY);
      stmt.setString(2, String.valueOf(version));
      stmt.setDouble(3, epochSeconds(updatedAt));
      stmt.executeUpdate();
    } catch (SQLException e) {
      throw new IndexWriteException("Save scan logic version failed", e);
    }
  }

  @Override
  public void writeNormalizedArtifact(
      NormalizedSessionArtifact artifact,
      Path artifactPath,
      String sourcePath,
      double sourceMtime,
      long sizeBytes,
      Instant indexedAt) {
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(artifactPath, "artifactPath 不得为 null");
    Objects.requireNonNull(sourcePath, "sourcePath 不得为 null");
    Objects.requireNonNull(indexedAt, "indexedAt 不得为 null");

    SessionRow sessionRow = ArtifactRowMapper.toSessionRow(artifact, sourceMtime, sourcePath);
    SessionArtifactRow artifactRow =
        ArtifactRowMapper.toArtifactRow(
            sessionRow.sessionKey(),
            artifactPath.toString(),
            artifact.schemaVersion(),
            sourcePath,
            sourceMtime,
            sizeBytes,
            epochSeconds(indexedAt));
    addSessionInsert(sessionRow);
    addArtifactInsert(artifactRow);
  }

  @Override
  public void writeMissingTranscriptSession(MissingTranscriptSession session) {
    Objects.requireNonNull(session, "session 不得为 null");
    double indexedAt = epochSeconds(session.indexedAt());
    SessionRow row =
        new SessionRow(
            session.sessionKey(),
            session.agent(),
            session.sessionId(),
            session.title(),
            session.projectKey(),
            session.projectName(),
            session.cwd(),
            session.endedAt(),
            session.endedAt(),
            0,
            0,
            0,
            session.model(),
            "",
            session.source(),
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            indexedAt,
            0,
            "");
    addSessionInsert(row);
  }

  @Override
  public int pendingWriteCount() {
    return batch.pendingCount();
  }

  @Override
  public void flushPendingWrites() {
    try {
      batch.flush();
    } catch (SQLException e) {
      throw new IndexWriteException("Index write flush failed", e);
    }
  }

  private void finishScan(
      long scanLogId, double finishedAt, Map<String, Integer> perSourceCount, String status) {
    Map<String, Integer> counts = perSourceCount == null ? Map.of() : perSourceCount;
    String sql =
        "UPDATE scan_log SET finished_at = ?, status = ?,"
            + " claude_count = ?, codex_count = ?, qoder_count = ? WHERE id = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, finishedAt);
      stmt.setString(2, status);
      stmt.setInt(3, counts.getOrDefault("claude_code", 0));
      stmt.setInt(4, counts.getOrDefault("codex", 0));
      stmt.setInt(5, counts.getOrDefault("qoder", 0));
      stmt.setLong(6, scanLogId);
      stmt.executeUpdate();
    } catch (SQLException e) {
      throw new IndexWriteException("scan_log finish failed", e);
    }
  }

  private long lastInsertRowId() throws SQLException {
    try (PreparedStatement stmt = conn.prepareStatement("SELECT last_insert_rowid()");
        ResultSet rs = stmt.executeQuery()) {
      if (rs.next()) {
        return rs.getLong(1);
      }
      return 0;
    }
  }

  private void addSessionInsert(SessionRow row) {
    StringBuilder sb = new StringBuilder(SESSION_INSERT_PREFIX);
    appendSqlValue(sb, row.sessionKey()).append(", ");
    appendSqlValue(sb, row.agent()).append(", ");
    appendSqlValue(sb, row.sessionId()).append(", ");
    appendSqlValue(sb, row.title()).append(", ");
    appendSqlValue(sb, row.projectKey()).append(", ");
    appendSqlValue(sb, row.projectName()).append(", ");
    appendSqlValue(sb, row.cwd()).append(", ");
    appendSqlValue(sb, row.startedAt()).append(", ");
    appendSqlValue(sb, row.endedAt()).append(", ");
    sb.append(row.durationSeconds()).append(", ");
    sb.append(row.modelExecutionSeconds()).append(", ");
    sb.append(row.toolExecutionSeconds()).append(", ");
    appendSqlValue(sb, row.model()).append(", ");
    appendSqlValue(sb, row.gitBranch()).append(", ");
    appendSqlValue(sb, row.source()).append(", ");
    sb.append(row.userMessageCount()).append(", ");
    sb.append(row.assistantMessageCount()).append(", ");
    sb.append(row.toolCallCount()).append(", ");
    sb.append(row.outputTokens()).append(", ");
    sb.append(row.freshInputTokens()).append(", ");
    sb.append(row.cacheReadTokens()).append(", ");
    sb.append(row.cacheWriteTokens()).append(", ");
    sb.append(row.totalTokens()).append(", ");
    sb.append(row.failedToolCount()).append(", ");
    sb.append(row.subagentInstanceCount()).append(", ");
    sb.append(row.indexedAt()).append(", ");
    sb.append(row.fileMtime()).append(", ");
    appendSqlValue(sb, row.filePath());
    sb.append(")");
    batch.add(sb.toString());
  }

  private void addArtifactInsert(SessionArtifactRow row) {
    StringBuilder sb = new StringBuilder(ARTIFACT_INSERT_PREFIX);
    appendSqlValue(sb, row.sessionKey()).append(", ");
    appendSqlValue(sb, row.artifactType()).append(", ");
    appendSqlValue(sb, row.path()).append(", ");
    appendSqlValue(sb, row.schemaVersion()).append(", ");
    appendSqlValue(sb, row.sourcePath()).append(", ");
    sb.append(row.sourceMtime()).append(", ");
    sb.append(row.sizeBytes()).append(", ");
    sb.append(row.createdAt()).append(", ");
    sb.append(row.updatedAt());
    sb.append(")");
    batch.add(sb.toString());
  }

  private static StringBuilder appendSqlValue(StringBuilder sb, String value) {
    sb.append("'");
    sb.append(value.replace("'", "''"));
    sb.append("'");
    return sb;
  }

  private static double epochSeconds(Instant instant) {
    return instant.getEpochSecond() + instant.getNano() / 1_000_000_000.0;
  }
}
