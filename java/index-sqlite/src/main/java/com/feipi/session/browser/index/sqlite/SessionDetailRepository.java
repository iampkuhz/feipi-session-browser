package com.feipi.session.browser.index.sqlite;

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
 * SessionQueryRepository#getSession}，避免重复 SQL。 所有 SQL 使用参数化绑定，用户输入仅作为参数。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>sessionKey 格式由 {@link SessionDetailRequest} 在入口完成校验。
 *   <li>本类信任已验证的 typed request，只负责 SQL 拼接和参数绑定。
 * </ul>
 */
public final class SessionDetailRepository {

  private final SessionQueryRepository sessionQueryRepository;

  /**
   * 使用已有 {@link SessionQueryRepository} 创建仓库。
   *
   * <p>会话行查找委托给 {@code SessionQueryRepository}，避免重复同一 SQL。
   *
   * @param sessionQueryRepository 会话查询仓库，schema 必须已就绪
   */
  public SessionDetailRepository(SessionQueryRepository sessionQueryRepository) {
    this.sessionQueryRepository =
        Objects.requireNonNull(sessionQueryRepository, "sessionQueryRepository 不得为 null");
  }

  /**
   * 按主键查找会话行数据。
   *
   * <p>委托给 {@link SessionQueryRepository#getSession}，与 list/search/count 共享同一查询逻辑。
   *
   * @param sessionKey 会话主键，格式 {@code agent:session_id}
   * @return 匹配的行，不存在时返回 empty
   * @throws SQLException 查询失败
   */
  public Optional<SessionRow> findSessionRow(String sessionKey) throws SQLException {
    return sessionQueryRepository.getSession(sessionKey);
  }

  /**
   * 查询会话关联的全部归一化制品行。
   *
   * <p>从 {@code session_artifacts} 表查找指定会话的全部制品记录，返回路径和元数据信息。
   *
   * @param sessionKey 会话主键
   * @return 制品行列表，可能为空
   * @throws SQLException 查询失败
   */
  public List<SessionArtifactRow> findArtifacts(String sessionKey) throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    String sql =
        "SELECT session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at"
            + " FROM session_artifacts WHERE session_key = ? ORDER BY artifact_type";
    List<SessionArtifactRow> rows = new ArrayList<>();
    try (ReadTransaction rt = sessionQueryRepository.indexConnection().readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setString(1, sessionKey);
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
   * <p>从 {@code session_artifacts} 表中查找类型为 {@code normalized} 的制品。
   *
   * @param sessionKey 会话主键
   * @return 归一化制品行，不存在时返回 empty
   * @throws SQLException 查询失败
   */
  public Optional<SessionArtifactRow> findNormalizedArtifact(String sessionKey)
      throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    String sql =
        "SELECT session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at"
            + " FROM session_artifacts"
            + " WHERE session_key = ? AND artifact_type = ?";
    try (ReadTransaction rt = sessionQueryRepository.indexConnection().readTransaction();
        PreparedStatement ps = rt.connection().prepareStatement(sql)) {
      ps.setString(1, sessionKey);
      ps.setString(2, ArtifactRowMapper.ARTIFACT_TYPE_NORMALIZED);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return Optional.of(mapArtifactRow(rs));
        }
        return Optional.empty();
      }
    }
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
