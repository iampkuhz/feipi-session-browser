package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.artifact.normalized.ArtifactConstants;
import com.feipi.session.browser.artifact.normalized.SafeArtifactName;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 已索引会话的数据库和 artifact 清理器。
 *
 * <p>提供两个核心操作：
 *
 * <ul>
 *   <li>{@link #deleteSession} — 删除单个会话的 session_artifacts 和 sessions 行。
 *   <li>{@link #deleteOrphanArtifacts} — 删除无对应 DB row 的 artifact 文件。
 * </ul>
 *
 * <p>删除顺序：先 {@code session_artifacts}，后 {@code sessions}，保证外键约束一致性。
 *
 * <p>所有操作幂等：对不存在的 session key 或 artifact 文件不报错。 失败时记录错误并返回，不中断后续操作。
 */
final class SessionDeleter {

  private static final Logger log = LoggerFactory.getLogger(SessionDeleter.class);

  /** 防止实例化。 */
  private SessionDeleter() {}

  /**
   * 删除单个会话的全部索引数据。
   *
   * <p>先删除 {@code session_artifacts} 表中的关联行，再删除 {@code sessions} 表中的主行。
   * 两次删除均在同一个事务上下文中执行（由调用方管理事务）。
   *
   * <p>幂等：session_key 不存在时不报错。
   *
   * @param conn SQLite 写连接
   * @param sessionKey 要删除的会话主键
   * @return 实际删除的 sessions 行数（0 或 1）
   * @throws SQLException SQL 执行失败
   */
  static int deleteSession(Connection conn, String sessionKey) throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");

    // 先删除关联的 artifact 行
    String artifactSql = "DELETE FROM session_artifacts WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(artifactSql)) {
      stmt.setString(1, sessionKey);
      stmt.executeUpdate();
    }

    // 再删除 sessions 行
    String sessionSql = "DELETE FROM sessions WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sessionSql)) {
      stmt.setString(1, sessionKey);
      return stmt.executeUpdate();
    }
  }

  /**
   * 更新已索引会话的文件路径（用于重命名检测后更新）。
   *
   * <p>同时更新 {@code file_path} 和 {@code file_mtime}（使用新文件的 mtime）。
   *
   * @param conn SQLite 写连接
   * @param sessionKey 会话主键
   * @param newFilePath 新文件路径
   * @param newFileMtime 新文件的 mtime（epoch 秒）
   * @return 实际更新的行数
   * @throws SQLException SQL 执行失败
   */
  static int updateSessionPath(
      Connection conn, String sessionKey, String newFilePath, double newFileMtime)
      throws SQLException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(newFilePath, "newFilePath 不得为 null");

    String sql = "UPDATE sessions SET file_path = ?, file_mtime = ? WHERE session_key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, newFilePath);
      stmt.setDouble(2, newFileMtime);
      stmt.setString(3, sessionKey);
      return stmt.executeUpdate();
    }
  }

  /**
   * 删除无对应 DB row 的 artifact 文件。
   *
   * <p>扫描 {@code artifactDir} 下所有 {@code *.json} 文件（排除 meta 文件和临时文件）， 检查是否存在对应的 DB
   * row。若不存在则删除数据文件和关联的 meta 文件。
   *
   * <p>幂等：文件不存在时不报错。
   *
   * @param artifactDir artifact 输出目录
   * @param validSessionKeys 当前 DB 中有效的 session key 集合
   * @param errors 收集执行过程中的错误信息
   * @return 成功删除的孤儿 artifact 数据文件数量
   */
  static int deleteOrphanArtifacts(
      Path artifactDir, Set<String> validSessionKeys, List<String> errors) {
    Objects.requireNonNull(artifactDir, "artifactDir 不得为 null");
    Objects.requireNonNull(validSessionKeys, "validSessionKeys 不得为 null");
    Objects.requireNonNull(errors, "errors 不得为 null");

    if (!Files.isDirectory(artifactDir)) {
      return 0;
    }

    int orphanCount = 0;
    List<Path> dataFiles = new ArrayList<>();

    try (var stream = Files.list(artifactDir)) {
      stream
          .filter(
              p -> {
                String name = p.getFileName().toString();
                return name.endsWith(ArtifactConstants.DATA_FILE_SUFFIX)
                    && !name.endsWith(ArtifactConstants.META_FILE_SUFFIX)
                    && !name.startsWith(ArtifactConstants.TEMP_FILE_PREFIX);
              })
          .forEach(dataFiles::add);
    } catch (IOException e) {
      errors.add("列出 artifact 目录失败: " + artifactDir + ": " + e.getMessage());
      return 0;
    }

    for (Path dataFile : dataFiles) {
      String fileName = dataFile.getFileName().toString();
      // 去掉 .json 后缀得到 safe name
      String safeName =
          fileName.substring(0, fileName.length() - ArtifactConstants.DATA_FILE_SUFFIX.length());
      String sessionKey = recoverSessionKeyFromSafeName(safeName, validSessionKeys);

      if (sessionKey == null || !validSessionKeys.contains(sessionKey)) {
        // 孤儿 artifact：无对应 DB row
        try {
          Files.deleteIfExists(dataFile);
          // 删除关联的 meta 文件
          Path metaFile = artifactDir.resolve(safeName + ArtifactConstants.META_FILE_SUFFIX);
          Files.deleteIfExists(metaFile);
          orphanCount++;
          log.info("删除孤儿 artifact: {}", dataFile.getFileName());
        } catch (IOException e) {
          errors.add("删除孤儿 artifact 失败: " + dataFile + ": " + e.getMessage());
        }
      }
    }

    return orphanCount;
  }

  /**
   * 从 safe artifact name 反向查找原始 session key。
   *
   * <p>由于 safe name 是 hash/清洗后的结果，无法完美反向映射。 这里通过遍历 validSessionKeys 并检查其 safe name 来匹配。当找不到匹配时返回
   * null。
   *
   * @param safeName safe artifact name（不含扩展名）
   * @param validSessionKeys 有效 session key 集合（当前 DB 中存在的）
   * @return 匹配的 session key，无匹配时返回 null
   */
  private static String recoverSessionKeyFromSafeName(
      String safeName, Set<String> validSessionKeys) {
    // 通过遍历 validSessionKeys 来匹配 safe name
    // 这是唯一可靠的方式，因为 safe name 是单向 hash/清洗
    for (String sessionKey : validSessionKeys) {
      try {
        String candidateSafeName = SafeArtifactName.sanitize(sessionKey);
        if (candidateSafeName.equals(safeName)) {
          return sessionKey;
        }
      } catch (IllegalArgumentException e) {
        // 某些 session key 可能无法安全清洗，跳过
      }
    }
    return null;
  }
}
