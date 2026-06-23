package com.feipi.session.browser.source.codex;

import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Codex 线程 SQLite 数据库只读访问器。
 *
 * <p>从 Codex 会话目录中的 {@code threads.sqlite3} 文件读取线程信息。 所有访问均以只读模式打开。
 *
 * <p>提供两种 API：
 *
 * <ul>
 *   <li>{@link #readThreads(Path)} — 简化 API，出错时返回空列表（向后兼容）。
 *   <li>{@link #readThreadsWithDiagnostics(Path)} — 诊断感知 API，出错时返回 {@link ThreadsDbResult}，其中携带
 *       {@link SourceDiagnostic} 描述错误原因。
 * </ul>
 *
 * <p>该类是不可变的，线程安全。
 */
public final class ThreadsDbReader {

  private static final Logger LOG = Logger.getLogger(ThreadsDbReader.class.getName());

  /** JDBC 连接超时时间（毫秒）。 */
  private static final int CONNECTION_TIMEOUT_MS = 5000;

  /** 线程查询 SQL。 */
  private static final String THREADS_QUERY = "SELECT * FROM threads LIMIT 10000";

  private ThreadsDbReader() {
    // 工具类，禁止实例化
  }

  /**
   * 从指定 SQLite 数据库路径读取线程信息（简化 API）。
   *
   * <p>使用 JDBC 只读模式打开数据库，读取 {@code threads} 表的所有列。 数据库不存在、锁定、缺列或发生任何错误时，返回空列表而不抛出异常。
   *
   * <p>需要诊断信息时请使用 {@link #readThreadsWithDiagnostics(Path)}。
   *
   * @param dbPath 数据库文件路径
   * @return 线程信息列表，每个线程为列名到值的映射；出错时返回空列表
   */
  public static List<Map<String, String>> readThreads(Path dbPath) {
    return readThreadsWithDiagnostics(dbPath).threads();
  }

  /**
   * 从指定 SQLite 数据库路径读取线程信息，携带诊断结果。
   *
   * <p>SQLite 错误不静默返回空列表，而是通过 {@link ThreadsDbResult#diagnostic()} 返回 错误描述。
   * 数据库文件不存在时视为正常情况（非错误），返回空结果且无诊断。
   *
   * @param dbPath 数据库文件路径
   * @return 包含线程数据和可选诊断的读取结果
   */
  public static ThreadsDbResult readThreadsWithDiagnostics(Path dbPath) {
    // 数据库文件不存在 — 正常情况，无诊断
    if (dbPath == null || !Files.isRegularFile(dbPath)) {
      return new ThreadsDbResult(Collections.emptyList(), Optional.empty());
    }

    // 加载 SQLite JDBC 驱动
    try {
      Class.forName("org.sqlite.JDBC");
    } catch (ClassNotFoundException e) {
      LOG.log(Level.FINE, "SQLite JDBC 驱动不可用", e);
      SourceDiagnostic diag =
          new SourceDiagnostic(
              ParseSeverity.ERROR,
              ParseIssueType.BAD_JSON,
              "SQLite JDBC 驱动不可用: " + e.getMessage(),
              1,
              Optional.empty(),
              CodexConstants.DIAG_CODE_DRIVER_MISSING,
              dbPath.toAbsolutePath().toString(),
              OptionalInt.empty(),
              OptionalInt.empty(),
              OptionalInt.empty());
      return new ThreadsDbResult(Collections.emptyList(), Optional.of(diag));
    }

    String url = "jdbc:sqlite:" + dbPath.toAbsolutePath() + "?mode=ro";
    Properties props = new Properties();
    props.setProperty("open_mode", "1"); // 只读模式
    props.setProperty("busy_timeout", String.valueOf(CONNECTION_TIMEOUT_MS));

    try (Connection conn = DriverManager.getConnection(url, props);
        Statement stmt = conn.createStatement()) {
      stmt.setQueryTimeout(CONNECTION_TIMEOUT_MS / 1000);

      List<Map<String, String>> results = new java.util.ArrayList<>();
      try (ResultSet rs = stmt.executeQuery(THREADS_QUERY)) {
        ResultSetMetaData meta = rs.getMetaData();
        int columnCount = meta.getColumnCount();

        while (rs.next()) {
          Map<String, String> row = new LinkedHashMap<>(columnCount);
          for (int i = 1; i <= columnCount; i++) {
            String colName = meta.getColumnName(i);
            String value = rs.getString(i);
            row.put(colName, value != null ? value : "");
          }
          results.add(row);
        }
      }
      return new ThreadsDbResult(Collections.unmodifiableList(results), Optional.empty());
    } catch (SQLException e) {
      LOG.log(Level.FINE, "读取 threads 数据库失败: " + dbPath, e);
      SourceDiagnostic diag =
          new SourceDiagnostic(
              ParseSeverity.ERROR,
              ParseIssueType.BAD_JSON,
              "SQLite 读取失败: " + e.getMessage(),
              1,
              Optional.empty(),
              CodexConstants.DIAG_CODE_SQLITE_ERROR,
              dbPath.toAbsolutePath().toString(),
              OptionalInt.empty(),
              OptionalInt.empty(),
              OptionalInt.empty());
      return new ThreadsDbResult(Collections.emptyList(), Optional.of(diag));
    }
  }
}
