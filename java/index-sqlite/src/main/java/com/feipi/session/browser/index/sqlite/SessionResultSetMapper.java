package com.feipi.session.browser.index.sqlite;

import java.sql.ResultSet;
import java.sql.SQLException;

/**
 * JDBC {@link ResultSet} 到 {@link SessionRow} 的行映射器。
 *
 * <p>显式列出全部 sessions 表列，不使用 {@code SELECT *}。 所有查询共享同一个映射逻辑，避免列名和类型不一致。
 *
 * <p>映射职责：
 *
 * <ul>
 *   <li>按列名读取，保证列顺序独立于 SELECT 列表。
 *   <li>字符串字段 null 转为空字符串，与 {@link SessionRow} 紧凑构造器一致。
 *   <li>数值字段直接读取，{@link SessionRow} 构造器负责非负校验。
 * </ul>
 */
final class SessionResultSetMapper {

  /** sessions 表全部列的显式列表，用于 SELECT 子句。 */
  static final String ALL_COLUMNS =
      "session_key, agent, session_id, title, project_key, project_name, cwd,"
          + " started_at, ended_at, duration_seconds, model_execution_seconds,"
          + " tool_execution_seconds, model, git_branch, source,"
          + " user_message_count, assistant_message_count, tool_call_count,"
          + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
          + " total_tokens, failed_tool_count, subagent_instance_count,"
          + " indexed_at, file_mtime, file_path";

  /** 防止实例化。 */
  private SessionResultSetMapper() {}

  /**
   * 将当前 ResultSet 行映射为 {@link SessionRow}。
   *
   * <p>调用方必须确保 ResultSet 已前进到有效行。 字符串 null 转为空字符串，与 {@link SessionRow} 紧凑构造器的默认值语义一致。
   *
   * @param rs 已定位到有效行的 ResultSet
   * @return 完整的 sessions 表行
   * @throws SQLException 读取列失败
   */
  static SessionRow mapRow(ResultSet rs) throws SQLException {
    return new SessionRow(
        rs.getString("session_key"),
        rs.getString("agent"),
        rs.getString("session_id"),
        nullToEmpty(rs.getString("title")),
        nullToEmpty(rs.getString("project_key")),
        nullToEmpty(rs.getString("project_name")),
        nullToEmpty(rs.getString("cwd")),
        nullToEmpty(rs.getString("started_at")),
        rs.getString("ended_at"),
        rs.getDouble("duration_seconds"),
        rs.getDouble("model_execution_seconds"),
        rs.getDouble("tool_execution_seconds"),
        nullToEmpty(rs.getString("model")),
        nullToEmpty(rs.getString("git_branch")),
        nullToEmpty(rs.getString("source")),
        rs.getLong("user_message_count"),
        rs.getLong("assistant_message_count"),
        rs.getLong("tool_call_count"),
        rs.getLong("output_tokens"),
        rs.getLong("fresh_input_tokens"),
        rs.getLong("cache_read_tokens"),
        rs.getLong("cache_write_tokens"),
        rs.getLong("total_tokens"),
        rs.getLong("failed_tool_count"),
        rs.getLong("subagent_instance_count"),
        rs.getDouble("indexed_at"),
        rs.getDouble("file_mtime"),
        nullToEmpty(rs.getString("file_path")));
  }

  private static String nullToEmpty(String value) {
    return value == null ? "" : value;
  }
}
