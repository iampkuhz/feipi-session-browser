package com.feipi.session.browser.index.store.sqlite.repository;

import com.feipi.session.browser.index.api.IndexQueryException;
import com.feipi.session.browser.index.api.query.SessionArtifactRecord;
import com.feipi.session.browser.index.api.query.SessionDetailPort;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.index.store.sqlite.mapper.ArtifactRowMapper;
import com.feipi.session.browser.index.store.sqlite.row.SessionArtifactRow;
import com.feipi.session.browser.index.store.sqlite.tx.ReadTransaction;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * 会话详情查询仓库。
 *
 * <p>提供 session detail 页面所需的数据库层查询：归一化制品元数据查询。 会话行查找复用 {@link
 * SqliteSessionQueryRepository#getSession}，避免重复 SQL。 所有 SQL 使用参数化绑定，用户输入仅作为参数。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>sessionKey 格式由 {@code SessionDetailRequest} 在入口完成校验。
 *   <li>本类信任已验证的 typed request，只负责 SQL 拼接和参数绑定。
 * </ul>
 */
public final class SqliteSessionDetailRepository implements SessionDetailPort {

  private final SqliteSessionQueryRepository sessionQueryRepository;

  /**
   * 封装一次可能抛出 {@link SQLException} 的只读查询。
   *
   * @param <T> 查询结果类型
   */
  @FunctionalInterface
  private interface SqlQuery<T> {
    T execute() throws SQLException;
  }

  /**
   * 使用已有 {@link SqliteSessionQueryRepository} 创建仓库。
   *
   * <p>会话行查找委托给 {@code SqliteSessionQueryRepository}，避免重复同一 SQL。
   *
   * @param sessionQueryRepository 会话查询仓库，schema 必须已就绪
   */
  public SqliteSessionDetailRepository(SqliteSessionQueryRepository sessionQueryRepository) {
    this.sessionQueryRepository =
        Objects.requireNonNull(sessionQueryRepository, "sessionQueryRepository 不得为 null");
  }

  private static <T> T execute(String operation, SqlQuery<T> query) {
    try {
      return query.execute();
    } catch (SQLException e) {
      throw new IndexQueryException("SQLite session detail query failed: " + operation, e);
    }
  }

  /**
   * 按主键查找会话行数据。
   *
   * <p>委托给 {@link SqliteSessionQueryRepository#getSession}，与 list/search/count 共享同一查询逻辑。
   *
   * @param sessionKey 会话主键，格式 {@code agent:session_id}
   * @return 匹配的行，不存在时返回 empty
   */
  @Override
  public Optional<SessionRecord> findSession(String sessionKey) {
    return sessionQueryRepository.getSession(sessionKey);
  }

  /**
   * 按主键查找会话行数据。
   *
   * <p>保留原 repository API 供既有调用方使用。
   *
   * @param sessionKey 会话主键，格式 {@code agent:session_id}
   * @return 匹配的行，不存在时返回 empty
   */
  public Optional<SessionRecord> findSessionRow(String sessionKey) {
    return findSession(sessionKey);
  }

  /**
   * 查询会话关联的全部归一化制品行。
   *
   * <p>从 {@code session_artifacts} 表查找指定会话的全部制品记录，返回路径和元数据信息。
   *
   * @param sessionKey 会话主键
   * @return 制品行列表，可能为空
   */
  @Override
  public List<SessionArtifactRecord> findArtifacts(String sessionKey) {
    return execute(
        "find artifacts", () -> new ArrayList<SessionArtifactRecord>(findArtifactsSql(sessionKey)));
  }

  private List<SessionArtifactRow> findArtifactsSql(String sessionKey) throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    String effectiveSessionKey = resolveStoredSessionKey(sessionKey);
    String sql =
        "SELECT session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at"
            + " FROM session_artifacts WHERE session_key = ? ORDER BY artifact_type";
    List<SessionArtifactRow> rows = new ArrayList<>();
    try (ReadTransaction rt = sessionQueryRepository.indexConnection().readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setString(1, effectiveSessionKey);
      try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
          rows.add(mapArtifactRow(rs));
        }
      }
    }
    return rows;
  }

  /**
   * 查找会话的归一化制品行。
   *
   * <p>从 {@code session_artifacts} 表中查找归一化制品。当前 Java scan 写入 {@code normalized}， main/Python-era
   * 索引历史上写入 {@code normalized_session_json}。详情页读取兼容两者，优先使用当前 Java 类型。
   *
   * @param sessionKey 会话主键
   * @return 归一化制品行，不存在时返回 empty
   */
  @Override
  public Optional<SessionArtifactRecord> findNormalizedArtifact(String sessionKey) {
    return execute(
        "find normalized artifact",
        () -> findNormalizedArtifactSql(sessionKey).map(row -> (SessionArtifactRecord) row));
  }

  private Optional<SessionArtifactRow> findNormalizedArtifactSql(String sessionKey)
      throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    String effectiveSessionKey = resolveStoredSessionKey(sessionKey);
    String sql =
        "SELECT session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at"
            + " FROM session_artifacts"
            + " WHERE session_key = ? AND artifact_type IN (?, ?)"
            + " ORDER BY CASE artifact_type WHEN ? THEN 0 ELSE 1 END"
            + " LIMIT 1";
    try (ReadTransaction rt = sessionQueryRepository.indexConnection().readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setString(1, effectiveSessionKey);
      ps.setString(2, ArtifactRowMapper.ARTIFACT_TYPE_NORMALIZED);
      ps.setString(3, ArtifactRowMapper.ARTIFACT_TYPE_NORMALIZED_SESSION_JSON);
      ps.setString(4, ArtifactRowMapper.ARTIFACT_TYPE_NORMALIZED);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return Optional.of(mapArtifactRow(rs));
        }
        return Optional.empty();
      }
    }
  }

  private String resolveStoredSessionKey(String routeSessionKey) throws SQLException {
    Optional<SessionRecord> row = sessionQueryRepository.getSession(routeSessionKey);
    return row.map(SessionRecord::sessionKey).orElse(routeSessionKey);
  }

  /**
   * 将当前 ResultSet 行映射为 {@link SessionArtifactRow}。
   *
   * <p>{@code findArtifacts} 和 {@code findNormalizedArtifact} 共享同一映射逻辑。
   */
  private static SessionArtifactRow mapArtifactRow(ResultSet rs) throws SQLException {
    return new SessionArtifactRow(
        rs.getString("session_key"),
        rs.getString("artifact_type"),
        rs.getString("path"),
        rs.getString("schema_version"),
        rs.getString("source_path"),
        rs.getDouble("source_mtime"),
        rs.getLong("size_bytes"),
        rs.getDouble("created_at"),
        rs.getDouble("updated_at"));
  }
}
