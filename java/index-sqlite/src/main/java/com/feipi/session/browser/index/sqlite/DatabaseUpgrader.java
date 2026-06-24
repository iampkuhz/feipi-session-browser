package com.feipi.session.browser.index.sqlite;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 数据库升级编排器，负责安全的 schema migration 全流程。
 *
 * <p>升级流程：
 *
 * <ol>
 *   <li>版本兼容性检查 — 拒绝降级和未来不兼容版本。
 *   <li>升级前原子备份 — 在 migration 前完整复制 DB 文件。
 *   <li>Schema migration — 通过 {@link IndexSchema#ensureSchema} 执行。
 *   <li>写入应用版本 — 记录当前 app version 到 index_metadata。
 *   <li>备份保留清理 — 删除超出上限的旧备份。
 * </ol>
 *
 * <p>失败恢复：migration 异常时自动从备份恢复 DB 文件，确保不丢失数据。 恢复操作本身失败时，原始异常和恢复异常均保留在抛出的 {@link UpgradeException}
 * 中。
 *
 * <p>校验放置：所有升级相关校验位于本类（upgrade manager 边界）。 schema 版本由 {@link MigrationRunner} 追踪，
 * 应用版本格式由本类构造器校验。下游 repository 不重复检查版本。
 *
 * <p>线程安全：本类实例不可变，但 {@link #upgrade} 方法操作文件系统， 并发调用同一数据库时行为未定义。调用方应通过外部锁（如 {@code ScanLock}）确保互斥。
 */
public final class DatabaseUpgrader {

  private static final Logger log = LoggerFactory.getLogger(DatabaseUpgrader.class);

  /** 备份文件最大保留数量。 */
  public static final int DEFAULT_BACKUP_RETENTION = 3;

  /** 备份文件前缀，位于备份目录下。 */
  public static final String BACKUP_FILE_PREFIX = "index-backup-";

  /** 备份文件后缀。 */
  public static final String BACKUP_FILE_SUFFIX = ".sqlite";

  /** index_metadata 表中存储应用版本的 key。 */
  public static final String APP_VERSION_KEY = "app_version";

  /** 备份时间格式，确保字典序与时间序一致。 */
  private static final DateTimeFormatter BACKUP_TIMESTAMP =
      DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneOffset.UTC);

  private final IndexSchema schema;
  private final String appVersion;
  private final Path backupDir;
  private final int backupRetention;

  /**
   * 创建数据库升级器。
   *
   * @param schema schema 入口，提供 migration runner 和 schema 操作
   * @param appVersion 当前应用版本，写入 index_metadata 供兼容性检查；null 或空时跳过版本追踪
   * @param backupDir 备份目录，升级前在此创建 DB 副本
   * @param backupRetention 备份保留数量上限，必须 &gt;= 1
   * @throws IllegalArgumentException retention &lt; 1
   * @throws NullPointerException schema 或 backupDir 为 null
   */
  public DatabaseUpgrader(
      IndexSchema schema, String appVersion, Path backupDir, int backupRetention) {
    this.schema = Objects.requireNonNull(schema, "schema 不得为 null");
    this.appVersion = (appVersion != null && !appVersion.isBlank()) ? appVersion : null;
    this.backupDir = Objects.requireNonNull(backupDir, "backupDir 不得为 null");
    if (backupRetention < 1) {
      throw new IllegalArgumentException("backupRetention 必须 >= 1，实际值: " + backupRetention);
    }
    this.backupRetention = backupRetention;
  }

  /**
   * 使用默认参数创建升级器。
   *
   * <p>默认参数：使用全部已注册 migration 的 {@link IndexSchema}， 备份保留 {@value #DEFAULT_BACKUP_RETENTION} 份。
   *
   * @param appVersion 应用版本，可为 null
   * @param backupDir 备份目录
   * @return 新升级器实例
   */
  public static DatabaseUpgrader withDefaults(String appVersion, Path backupDir) {
    return new DatabaseUpgrader(
        IndexSchema.withDefaults(), appVersion, backupDir, DEFAULT_BACKUP_RETENTION);
  }

  /**
   * 执行完整的数据库升级流程。
   *
   * <p>流程：
   *
   * <ol>
   *   <li>如果数据库文件不存在，仅运行 migration 创建 schema，不备份。
   *   <li>检查版本兼容性（拒绝降级和未来版本）。
   *   <li>创建备份。
   *   <li>运行 migration + 修复缺失列 + 创建索引。
   *   <li>写入应用版本到 index_metadata。
   *   <li>清理超额旧备份。
   * </ol>
   *
   * <p>migration 失败时自动从备份恢复 DB 文件。
   *
   * @param dbPath SQLite 数据库文件路径
   * @return 升级结果
   * @throws UpgradeException 版本不兼容、migration 失败或备份恢复失败
   */
  public UpgradeResult upgrade(Path dbPath) {
    Objects.requireNonNull(dbPath, "dbPath 不得为 null");

    // 数据库不存在时直接创建，无需备份
    if (!Files.exists(dbPath)) {
      return createFresh(dbPath);
    }

    Path backupPath = null;
    try (Connection conn = openConnection(dbPath)) {
      // 版本兼容性检查
      checkVersionCompatibility(conn);

      // 升级前备份
      backupPath = backupDatabase(dbPath);

      // 运行 migration
      List<SchemaVersion> applied = schema.ensureSchema(conn);
      boolean versionChanged = !applied.isEmpty();

      // 写入应用版本
      String recordedVersion = null;
      if (appVersion != null) {
        writeAppVersion(conn, appVersion);
        recordedVersion = appVersion;
      }

      // 清理旧备份
      pruneOldBackups();

      return new UpgradeResult(applied, backupPath, versionChanged, recordedVersion);

    } catch (SQLException e) {
      // migration 失败，尝试从备份恢复
      log.error("数据库升级失败，尝试从备份恢复", e);
      if (backupPath != null) {
        try {
          restoreFromBackup(backupPath, dbPath);
          log.info("已从备份恢复数据库: {}", backupPath);
        } catch (IOException restoreEx) {
          UpgradeException fatal = new UpgradeException("数据库升级失败且备份恢复失败: " + backupPath, e);
          fatal.addSuppressed(restoreEx);
          throw fatal;
        }
      }
      throw new UpgradeException("数据库升级失败: " + e.getMessage(), e);
    } catch (IOException e) {
      throw new UpgradeException("备份或恢复操作失败: " + e.getMessage(), e);
    }
  }

  /**
   * 创建全新数据库，无备份。
   *
   * <p>数据库文件不存在时，确保父目录存在后运行全部 migration。 不创建备份（没有需要保护的数据）。
   */
  private UpgradeResult createFresh(Path dbPath) {
    try {
      Path parent = dbPath.getParent();
      if (parent != null) {
        Files.createDirectories(parent);
      }
    } catch (IOException e) {
      throw new UpgradeException("创建数据库目录失败: " + e.getMessage(), e);
    }

    try (Connection conn = openConnection(dbPath)) {
      List<SchemaVersion> applied = schema.ensureSchema(conn);

      String recordedVersion = null;
      if (appVersion != null) {
        writeAppVersion(conn, appVersion);
        recordedVersion = appVersion;
      }

      return new UpgradeResult(applied, null, true, recordedVersion);
    } catch (SQLException e) {
      throw new UpgradeException("创建数据库失败: " + e.getMessage(), e);
    }
  }

  /**
   * 创建数据库备份文件。
   *
   * <p>使用 {@link StandardCopyOption#REPLACE_EXISTING} 和 {@link StandardCopyOption#COPY_ATTRIBUTES}
   * 确保原子复制。备份文件名包含 UTC 时间戳， 保证字典序与时间序一致，便于保留策略排序。
   *
   * @param dbPath 源数据库路径
   * @return 备份文件路径
   * @throws IOException 备份失败
   */
  private Path backupDatabase(Path dbPath) throws IOException {
    Files.createDirectories(backupDir);

    String timestamp = BACKUP_TIMESTAMP.format(Instant.now());
    String backupFileName = BACKUP_FILE_PREFIX + timestamp + BACKUP_FILE_SUFFIX;
    Path backupPath = backupDir.resolve(backupFileName);

    Files.copy(
        dbPath,
        backupPath,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);
    log.info("数据库已备份: {} -> {}", dbPath.getFileName(), backupPath);

    // 同步复制 WAL 和 SHM 文件（如果存在），确保备份数据一致性
    copyIfExists(
        dbPath.resolveSibling(dbPath.getFileName() + "-wal"),
        backupPath.resolveSibling(backupPath.getFileName() + "-wal"));
    copyIfExists(
        dbPath.resolveSibling(dbPath.getFileName() + "-shm"),
        backupPath.resolveSibling(backupPath.getFileName() + "-shm"));

    return backupPath;
  }

  /** 复制文件，源不存在时静默跳过。 */
  private static void copyIfExists(Path source, Path target) throws IOException {
    if (Files.exists(source)) {
      Files.copy(
          source, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES);
    }
  }

  /**
   * 从备份恢复数据库。
   *
   * <p>先删除可能损坏的数据库文件和 WAL/SHM 附属文件， 再从备份复制完整数据库。SQLite WAL 模式下关闭连接后 附属文件可能残留，必须一并清理。
   *
   * @param backupPath 备份文件路径
   * @param dbPath 目标数据库路径
   * @throws IOException 恢复失败
   */
  private static void restoreFromBackup(Path backupPath, Path dbPath) throws IOException {
    // 删除损坏的数据库及其 WAL/SHM 附属文件
    Files.deleteIfExists(dbPath);
    Files.deleteIfExists(dbPath.resolveSibling(dbPath.getFileName() + "-wal"));
    Files.deleteIfExists(dbPath.resolveSibling(dbPath.getFileName() + "-shm"));

    // 从备份恢复
    Files.copy(
        backupPath,
        dbPath,
        StandardCopyOption.REPLACE_EXISTING,
        StandardCopyOption.COPY_ATTRIBUTES);

    // 恢复 WAL/SHM 附属文件（如果备份中包含）
    copyIfExists(
        backupPath.resolveSibling(backupPath.getFileName() + "-wal"),
        dbPath.resolveSibling(dbPath.getFileName() + "-wal"));
    copyIfExists(
        backupPath.resolveSibling(backupPath.getFileName() + "-shm"),
        dbPath.resolveSibling(dbPath.getFileName() + "-shm"));
  }

  /**
   * 检查版本兼容性，拒绝降级和未来不兼容版本。
   *
   * <p>从 index_metadata 表读取上次写入的应用版本， 与当前版本比较。如果 DB 中的应用版本高于当前版本， 说明有人在降级运行，拒绝执行以防止数据损坏。
   *
   * <p>版本比较使用简单的字典序（适用于 semver 格式如 "0.4", "0.5", "1.0"）。 空或不可解析的版本跳过检查。
   *
   * @param conn 数据库连接
   * @throws SQLException 版本不兼容或查询失败
   */
  private void checkVersionCompatibility(Connection conn) throws SQLException {
    if (appVersion == null) {
      return;
    }

    // index_metadata 表可能不存在（全新数据库场景由 ensureSchema 创建）
    if (!metadataTableExists(conn)) {
      return;
    }

    String dbAppVersion = readMetadata(conn, APP_VERSION_KEY);
    if (dbAppVersion == null || dbAppVersion.isBlank()) {
      return;
    }

    // 字典序比较：适用于 semver 格式（major.minor）
    if (dbAppVersion.compareTo(appVersion) > 0) {
      throw new SQLException(
          "数据库由更新版本创建（DB: "
              + dbAppVersion
              + ", 当前: "
              + appVersion
              + "）。拒绝降级以防止数据损坏。"
              + "请使用匹配或更新版本的应用。");
    }
  }

  /**
   * 清理超过保留上限的旧备份。
   *
   * <p>按文件名字典序排序（等同于时间序），保留最新的 {@link #backupRetention} 份， 删除其余旧备份。删除单个备份失败时记录警告并继续，不中断升级流程。
   */
  private void pruneOldBackups() {
    List<Path> backups = listBackups();
    if (backups.size() <= backupRetention) {
      return;
    }

    // 按文件名字典序排序（时间戳格式保证字典序 = 时间序）
    backups.sort((a, b) -> a.getFileName().toString().compareTo(b.getFileName().toString()));

    int toDelete = backups.size() - backupRetention;
    for (int i = 0; i < toDelete; i++) {
      Path old = backups.get(i);
      try {
        Files.deleteIfExists(old);
        // 同时删除对应的 WAL/SHM 附属文件
        Files.deleteIfExists(old.resolveSibling(old.getFileName() + "-wal"));
        Files.deleteIfExists(old.resolveSibling(old.getFileName() + "-shm"));
        log.info("清理旧备份: {}", old.getFileName());
      } catch (IOException e) {
        log.warn("清理旧备份失败（可忽略）: {}", old, e);
      }
    }
  }

  /**
   * 列出备份目录中的全部备份文件。
   *
   * @return 备份文件路径列表，目录不存在时返回空列表
   */
  private List<Path> listBackups() {
    List<Path> backups = new ArrayList<>();
    if (!Files.isDirectory(backupDir)) {
      return backups;
    }
    try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(backupDir, BACKUP_FILE_PREFIX + "*" + BACKUP_FILE_SUFFIX)) {
      for (Path entry : stream) {
        if (Files.isRegularFile(entry)) {
          backups.add(entry);
        }
      }
    } catch (IOException e) {
      log.warn("列出备份文件失败: {}", backupDir, e);
    }
    return backups;
  }

  /**
   * 读取 index_metadata 表中指定 key 的值。
   *
   * @param conn 数据库连接
   * @param key 元数据 key
   * @return 对应的值，key 不存在或表不存在时返回 null
   * @throws SQLException 查询失败
   */
  private static String readMetadata(Connection conn, String key) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement("SELECT value FROM index_metadata WHERE key = ?")) {
      ps.setString(1, key);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return rs.getString(1);
        }
      }
    }
    return null;
  }

  /**
   * 写入应用版本到 index_metadata 表。
   *
   * <p>使用 INSERT OR REPLACE 确保幂等。 时间戳使用 SQLite {@code strftime('%s')} 获取 Unix epoch 秒。
   *
   * @param conn 数据库连接
   * @param version 应用版本字符串
   * @throws SQLException 写入失败
   */
  private static void writeAppVersion(Connection conn, String version) throws SQLException {
    try (PreparedStatement ps =
        conn.prepareStatement(
            "INSERT OR REPLACE INTO index_metadata (key, value, updated_at)"
                + " VALUES (?, ?, strftime('%s', 'now'))")) {
      ps.setString(1, APP_VERSION_KEY);
      ps.setString(2, version);
      ps.executeUpdate();
    }
  }

  /**
   * 检查 index_metadata 表是否存在。
   *
   * @param conn 数据库连接
   * @return 表存在时返回 true
   * @throws SQLException 查询失败
   */
  private static boolean metadataTableExists(Connection conn) throws SQLException {
    try (ResultSet rs =
        conn.getMetaData().getTables(null, null, "index_metadata", new String[] {"TABLE"})) {
      return rs.next();
    }
  }

  /** 打开 SQLite 连接并配置标准 PRAGMA。复用 {@link ConnectionFactory} 的统一 PRAGMA 应用逻辑。 */
  private static Connection openConnection(Path dbPath) throws SQLException {
    String jdbcUrl = "jdbc:sqlite:" + dbPath.toAbsolutePath();
    return new ConnectionFactory(jdbcUrl, PragmaConfig.DEFAULTS).create();
  }

  /**
   * 数据库升级异常。
   *
   * <p>表示升级流程中的不可恢复错误，包括版本不兼容、migration 失败和备份恢复失败。
   */
  public static final class UpgradeException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    /**
     * 创建升级异常。
     *
     * @param message 错误描述
     * @param cause 原始异常
     */
    public UpgradeException(String message, Throwable cause) {
      super(message, cause);
    }
  }
}
