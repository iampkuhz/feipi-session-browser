package com.feipi.session.browser.index.store.sqlite.repository;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.write.IndexWriteException;
import com.feipi.session.browser.index.api.write.IndexWriterPort;
import com.feipi.session.browser.index.api.write.MissingTranscriptSession;
import com.feipi.session.browser.index.api.write.ScanFailure;
import com.feipi.session.browser.index.api.write.StoredSessionFingerprint;
import com.feipi.session.browser.index.store.sqlite.mapper.ArtifactRowMapper;
import com.feipi.session.browser.index.store.sqlite.mapper.SessionTimingSqlMapper;
import com.feipi.session.browser.index.store.sqlite.mapper.TokenProvenanceSqlMapper;
import com.feipi.session.browser.index.store.sqlite.row.SessionArtifactRow;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.tx.WriteBatch;
import java.io.IOException;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.sql.Statement;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 扫描写侧索引端口的 SQLite 实现。 */
public final class SqliteIndexWriter implements IndexWriterPort {

  private static final String CANDIDATE_METADATA_PREFIX = "scan_candidate_metadata:";

  private static final String SCAN_LOGIC_VERSION_KEY = "scan_logic_version";

  private static final String SESSION_INSERT_PREFIX =
      "INSERT OR REPLACE INTO sessions ("
          + "session_key, agent, session_id, title, project_key, project_name, "
          + "cwd, started_at, ended_at, duration_seconds, model_execution_seconds, "
          + "tool_execution_seconds, model, git_branch, source, "
          + "user_message_count, assistant_message_count, tool_call_count, "
          + "output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens, "
          + "total_tokens, failed_tool_count, subagent_instance_count, "
          + "indexed_at, file_mtime, file_path, "
          + TokenProvenanceSqlMapper.COLUMNS
          + ", timing_json, round_count, llm_call_count, content_measured, user_message_measured,"
          + " assistant_message_measured) VALUES (";

  private static final String ARTIFACT_INSERT_PREFIX =
      "INSERT OR REPLACE INTO session_artifacts ("
          + "session_key, artifact_type, path, schema_version, source_path, "
          + "source_mtime, size_bytes, created_at, updated_at"
          + ") VALUES (";

  private final Connection conn;
  private final List<String> pending = new ArrayList<>();
  private Savepoint scanSavepoint;
  private boolean scanAutoCommit;
  private boolean publicationRequired;
  private boolean scanPriorPublicationRequired;

  /**
   * 使用调用方管理的 SQLite 连接创建写入器。
   *
   * <p>连接必须非 null 且保持打开；schema 可在后续通过 {@link #ensureSchema()} 初始化。
   *
   * @param conn 可用的 SQLite 连接
   * @throws NullPointerException 当连接为 null 时
   */
  public SqliteIndexWriter(Connection conn) {
    this.conn = Objects.requireNonNull(conn, "conn 不得为 null");
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
    try (Statement facts = conn.createStatement()) {
      for (String table : EventActivitySql.TABLES)
        publicationRequired |= facts.executeUpdate("DELETE FROM " + table) > 0;
    } catch (SQLException e) {
      throw new IndexWriteException("Clear event activity failed", e);
    }
    try (PreparedStatement artifacts = conn.prepareStatement("DELETE FROM session_artifacts")) {
      publicationRequired |= artifacts.executeUpdate() > 0;
      try (PreparedStatement metadata =
          conn.prepareStatement("DELETE FROM index_metadata WHERE substr(key, 1, ?) = ?")) {
        metadata.setInt(1, CANDIDATE_METADATA_PREFIX.length());
        metadata.setString(2, CANDIDATE_METADATA_PREFIX);
        publicationRequired |= metadata.executeUpdate() > 0;
      }
      try (PreparedStatement sessions = conn.prepareStatement("DELETE FROM sessions")) {
        publicationRequired |= sessions.executeUpdate() > 0;
      }
    } catch (SQLException e) {
      throw new IndexWriteException("Clear existing index failed", e);
    }
  }

  @Override
  public void clearExistingIndex(Set<String> agents) {
    Objects.requireNonNull(agents, "agents 不得为 null");
    if (agents.isEmpty()) {
      clearExistingIndex();
      return;
    }
    List<String> selected = List.copyOf(agents);
    String placeholders = String.join(",", Collections.nCopies(selected.size(), "?"));
    String selectedSessions =
        "SELECT session_key FROM sessions WHERE agent IN (" + placeholders + ")";
    List<String> deletes = new ArrayList<>();
    for (String table : EventActivitySql.TABLES)
      deletes.add("DELETE FROM " + table + " WHERE session_key IN (" + selectedSessions + ")");
    deletes.addAll(
        List.of(
            "DELETE FROM session_artifacts WHERE session_key IN (" + selectedSessions + ")",
            "DELETE FROM index_metadata WHERE key IN (SELECT '"
                + CANDIDATE_METADATA_PREFIX
                + "' || session_key FROM sessions WHERE agent IN ("
                + placeholders
                + "))",
            "DELETE FROM sessions WHERE agent IN (" + placeholders + ")"));
    try {
      for (String sql : deletes) {
        try (PreparedStatement statement = conn.prepareStatement(sql)) {
          for (int i = 0; i < selected.size(); i++) statement.setString(i + 1, selected.get(i));
          publicationRequired |= statement.executeUpdate() > 0;
        }
      }
    } catch (SQLException e) {
      throw new IndexWriteException("Clear selected agent index failed", e);
    }
  }

  @Override
  public long startScan(double startedAt, String mode) {
    Objects.requireNonNull(mode, "mode 不得为 null");
    if (scanSavepoint != null) throw new IllegalStateException("A scan is already active");
    String sql = "INSERT INTO scan_log (started_at, mode, status) VALUES (?, ?, 'running')";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, startedAt);
      stmt.setString(2, mode);
      stmt.executeUpdate();
      long id = lastInsertRowId();
      scanAutoCommit = conn.getAutoCommit();
      conn.setAutoCommit(false);
      scanSavepoint = conn.setSavepoint();
      scanPriorPublicationRequired = publicationRequired;
      publicationRequired |= !pending.isEmpty();
      return id;
    } catch (SQLException e) {
      throw new IndexWriteException("scan_log start failed", e);
    }
  }

  @Override
  public void completeScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount) {
    try {
      flushPendingWrites();
      finishScan(scanLogId, finishedAt, perSourceCount, "success");
      boolean hasGeneration;
      try (PreparedStatement statement =
              conn.prepareStatement(
                  "SELECT 1 FROM index_metadata WHERE key = 'published_generation'");
          ResultSet result = statement.executeQuery()) {
        hasGeneration = result.next();
      }
      if (publicationRequired || !hasGeneration) {
        try (PreparedStatement generation =
            conn.prepareStatement(
                "INSERT OR REPLACE INTO index_metadata(key, value, updated_at) VALUES"
                    + " ('published_generation', ?, ?)")) {
          generation.setString(1, java.util.UUID.randomUUID().toString());
          generation.setDouble(2, finishedAt);
          generation.executeUpdate();
        }
      }
      conn.commit();
      scanSavepoint = null;
      publicationRequired = false;
      conn.setAutoCommit(scanAutoCommit);
    } catch (SQLException e) {
      throw new IndexWriteException("Scan publication failed", e);
    }
  }

  @Override
  public void failScan(long scanLogId, double finishedAt, Map<String, Integer> perSourceCount) {
    failScan(scanLogId, finishedAt, perSourceCount, List.of(ScanFailure.generic()));
  }

  @Override
  public void failScan(
      long scanLogId,
      double finishedAt,
      Map<String, Integer> perSourceCount,
      List<ScanFailure> failures) {
    int errorCount =
        (int)
            failures.stream()
                .map(reason -> List.of(reason.source(), reason.sessionKey(), reason.phase()))
                .distinct()
                .count();
    failScan(scanLogId, finishedAt, perSourceCount, Math.max(1, errorCount), failures);
  }

  @Override
  public void failScan(
      long scanLogId,
      double finishedAt,
      Map<String, Integer> perSourceCount,
      int errorCount,
      List<ScanFailure> failures) {
    List<ScanFailure> reasons =
        failures.isEmpty() ? List.of(ScanFailure.generic()) : List.copyOf(failures);
    try {
      pending.clear();
      if (scanSavepoint != null) {
        conn.rollback(scanSavepoint);
        conn.releaseSavepoint(scanSavepoint);
        scanSavepoint = null;
      }
      publicationRequired = scanPriorPublicationRequired;
      finishScan(scanLogId, finishedAt, Map.of(), "failure");
      try (PreparedStatement details =
          conn.prepareStatement(
              "UPDATE scan_log SET error_count = ?, failures_json = ?, processed_count = ? WHERE id"
                  + " = ?")) {
        details.setInt(1, Math.max(1, errorCount));
        details.setString(
            2, new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(reasons));
        details.setInt(
            3,
            perSourceCount == null
                ? 0
                : perSourceCount.values().stream().mapToInt(Integer::intValue).sum());
        details.setLong(4, scanLogId);
        details.executeUpdate();
      }
      conn.commit();
      conn.setAutoCommit(scanAutoCommit);
    } catch (SQLException | com.fasterxml.jackson.core.JsonProcessingException e) {
      throw new IndexWriteException("Scan rollback failed", e);
    }
  }

  @Override
  public Map<String, StoredSessionFingerprint> loadStoredSessionFingerprints() {
    String sql =
        "SELECT session_key, file_path, file_mtime, agent, ended_at, title, project_key, cwd,"
            + " started_at, git_branch, model, source, COALESCE((SELECT value FROM index_metadata"
            + " WHERE key = '"
            + CANDIDATE_METADATA_PREFIX
            + "' || sessions.session_key), '')"
            + " AS candidate_metadata_fingerprint FROM sessions";
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
                rs.getString("ended_at"),
                rs.getString("title"),
                rs.getString("project_key"),
                rs.getString("cwd"),
                rs.getString("started_at"),
                rs.getString("git_branch"),
                rs.getString("model"),
                rs.getString("source"),
                rs.getString("candidate_metadata_fingerprint")));
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
    publicationRequired |= loadScanLogicVersion() != version;
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
    enqueueContentRows(
        sessionRow,
        artifactPath,
        artifact.schemaVersion(),
        artifact.session(),
        sizeBytes,
        indexedAt);
  }

  @Override
  public void writeNormalizedContent(
      NormalizedSessionContent content,
      Path artifactPath,
      String sourcePath,
      double sourceMtime,
      long sizeBytes,
      Instant indexedAt)
      throws IOException {
    Objects.requireNonNull(content, "content");
    Objects.requireNonNull(artifactPath, "artifactPath");
    Objects.requireNonNull(sourcePath, "sourcePath");
    Objects.requireNonNull(indexedAt, "indexedAt");
    SessionRow row = ArtifactRowMapper.toContentSessionRow(content, sourceMtime, sourcePath);
    enqueueContentRows(
        row,
        artifactPath,
        content.header().schemaVersion(),
        content.header().session(),
        sizeBytes,
        indexedAt);
  }

  private void enqueueContentRows(
      SessionRow sessionRow,
      Path artifactPath,
      String schemaVersion,
      Map<String, Object> session,
      long sizeBytes,
      Instant indexedAt) {
    if (session.containsKey("eventActivity") && session.get("eventActivity") == null) {
      throw new IllegalArgumentException("Present event activity metadata must be an object");
    }
    List<String> eventRows =
        EventActivitySql.replacement(sessionRow.sessionKey(), session.get("eventActivity"));
    SessionArtifactRow artifactRow =
        ArtifactRowMapper.toArtifactRow(
            sessionRow.sessionKey(),
            artifactPath.toString(),
            schemaVersion,
            sessionRow.filePath(),
            sessionRow.fileMtime(),
            sizeBytes,
            epochSeconds(indexedAt));
    pending.addAll(eventRows);
    addSessionInsert(sessionRow);
    addArtifactInsert(artifactRow);
    Object fingerprint = session.get("candidate_metadata_fingerprint");
    if (fingerprint instanceof String value) {
      StringBuilder metadata =
          new StringBuilder(
              "INSERT OR REPLACE INTO index_metadata(key, value, updated_at) VALUES (");
      appendSqlValue(metadata, CANDIDATE_METADATA_PREFIX + sessionRow.sessionKey()).append(", ");
      appendSqlValue(metadata, value).append(", ").append(epochSeconds(indexedAt)).append(')');
      pending.add(metadata.toString());
    }
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
            session.startedAt(),
            session.endedAt(),
            0,
            0,
            0,
            session.model(),
            session.gitBranch(),
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
    pending.addAll(EventActivitySql.replacement(session.sessionKey(), null));
    addSessionInsert(row);
  }

  @Override
  public int pendingWriteCount() {
    return pending.size();
  }

  @Override
  public void flushPendingWrites() {
    if (pending.isEmpty()) return;
    try {
      if (scanSavepoint == null) {
        WriteBatch.executeInTransaction(conn, c -> executePending());
      } else {
        executePending();
      }
      pending.clear();
    } catch (SQLException e) {
      throw new IndexWriteException("Index write flush failed", e);
    }
  }

  private void executePending() throws SQLException {
    try (Statement statement = conn.createStatement()) {
      for (String sql : pending) statement.execute(sql);
    }
  }

  private void finishScan(
      long scanLogId, double finishedAt, Map<String, Integer> perSourceCount, String status) {
    Map<String, Integer> counts = perSourceCount == null ? Map.of() : perSourceCount;
    String sql =
        "UPDATE scan_log SET finished_at = ?, status = ?, claude_count = ?, codex_count = ?,"
            + " qoder_count = ?, processed_count = ? WHERE id = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, finishedAt);
      stmt.setString(2, status);
      stmt.setInt(3, counts.getOrDefault("claude_code", 0));
      stmt.setInt(4, counts.getOrDefault("codex", 0));
      stmt.setInt(5, counts.getOrDefault("qoder", 0));
      stmt.setInt(6, counts.values().stream().mapToInt(Integer::intValue).sum());
      stmt.setLong(7, scanLogId);
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
    publicationRequired = true;
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
    appendSqlValue(sb, row.filePath()).append(", ");
    TokenProvenance provenance = row.tokenProvenance();
    appendSqlValue(sb, provenance.freshInput()).append(", ");
    appendSqlValue(sb, provenance.cacheRead()).append(", ");
    appendSqlValue(sb, provenance.cacheWrite()).append(", ");
    appendSqlValue(sb, provenance.output()).append(", ");
    appendSqlValue(sb, provenance.estimationMethod()).append(", ");
    sb.append(provenance.estimatedSessionCount() > 0 ? 1 : 0).append(", ");
    sb.append(provenance.unavailableSessionCount() > 0 ? 1 : 0).append(", ");
    sb.append(provenance.unknownSessionCount() > 0 ? 1 : 0).append(", ");
    appendSqlValue(sb, SessionTimingSqlMapper.encode(row.timing())).append(", ");
    sb.append(row.roundCount() == null ? "NULL" : row.roundCount()).append(", ");
    sb.append(row.llmCallCount() == null ? "NULL" : row.llmCallCount()).append(", ");
    sb.append(row.contentMeasured() ? 1 : 0).append(", ");
    sb.append(row.userMessageMeasured() ? 1 : 0).append(", ");
    sb.append(row.assistantMessageMeasured() ? 1 : 0);
    sb.append(")");
    pending.add(sb.toString());
  }

  private void addArtifactInsert(SessionArtifactRow row) {
    publicationRequired = true;
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
    pending.add(sb.toString());
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
