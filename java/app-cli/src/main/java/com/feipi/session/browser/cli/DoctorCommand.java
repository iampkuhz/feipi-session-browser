package com.feipi.session.browser.cli;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * doctor 子命令实现：环境诊断。
 *
 * <p>逐项检查运行环境，输出每项的状态和详情。doctor 不修改任何数据，仅做只读检查。
 *
 * <p>检查项：
 *
 * <ol>
 *   <li>Java 运行时版本
 *   <li>SQLite native library 加载
 *   <li>数据目录存在性和写权限
 *   <li>数据库文件完整性和可读性
 *   <li>默认端口可用性
 *   <li>PID 文件状态
 * </ol>
 *
 * <p>退出码：
 *
 * <ul>
 *   <li>0 — 所有检查通过
 *   <li>1 — 至少一项检查失败
 * </ul>
 *
 * <p>校验放置：各项检查在不同 trust boundary 执行一次，不在下游重复校验。 路径解析在 {@link PathResolver} 边界执行一次； 端口检查通过 TCP
 * 连接探测执行一次； DB 检查通过 JDBC 连接执行一次。
 */
@Command(
    name = "doctor",
    mixinStandardHelpOptions = true,
    description = "诊断运行环境",
    sortOptions = false)
final class DoctorCommand implements Callable<Integer> {

  private static final Logger LOG = LoggerFactory.getLogger(DoctorCommand.class);

  /** 默认端口，与 serve 命令一致。 */
  private static final int DEFAULT_PORT = 8848;

  /** 默认索引目录环境变量名。 */
  private static final String INDEX_DIR_ENV = "INDEX_DIR";

  /** 端口连接探测超时（毫秒）。 */
  private static final int PORT_PROBE_TIMEOUT_MS = 1000;

  @Option(
      names = {"--port", "-p"},
      description = "服务端口（默认 ${DEFAULT-VALUE}），用于端口可用性检查",
      defaultValue = "" + DEFAULT_PORT)
  private int port;

  @Option(
      names = {"--index-dir"},
      description = "索引目录（默认与 serve 相同）")
  private String indexDirOption;

  @Override
  public Integer call() {
    Path indexDir = PathResolver.resolveDataDir(indexDirOption, INDEX_DIR_ENV);
    List<CheckResult> results = new ArrayList<>();

    results.add(checkJavaRuntime());
    results.add(checkSqliteNative());
    results.add(checkDataDirectory(indexDir));
    results.add(checkDatabase(indexDir));
    results.add(checkPortAvailability());
    results.add(checkPidFile(indexDir));

    int failed = 0;
    for (CheckResult r : results) {
      String statusIcon = r.passed() ? "[OK]" : "[FAIL]";
      System.out.println(statusIcon + " " + r.name());
      if (!r.detail().isEmpty()) {
        System.out.println("     " + r.detail());
      }
      if (!r.passed()) {
        failed++;
      }
    }

    System.out.println();
    if (failed == 0) {
      System.out.println("诊断完成：所有检查通过。");
      return 0;
    } else {
      System.out.println("诊断完成：" + failed + " 项检查失败。");
      return 1;
    }
  }

  /**
   * 检查 Java 运行时版本。
   *
   * <p>验证当前 JVM 版本满足最低要求（Java 17+）。
   *
   * @return 检查结果
   */
  private static CheckResult checkJavaRuntime() {
    String version = System.getProperty("java.version", "unknown");
    String vendor = System.getProperty("java.vendor", "unknown");
    String vmName = System.getProperty("java.vm.name", "unknown");

    int majorVersion = parseMajorVersion(version);
    boolean passed = majorVersion >= 17;

    String detail = "版本 " + version + " (" + vendor + ", " + vmName + ")";
    return new CheckResult("Java 运行时", passed, detail);
  }

  /**
   * 检查 SQLite native library 是否可加载。
   *
   * <p>通过尝试加载 Xerial SQLite JDBC 驱动并建立内存连接验证 native library 可用。
   *
   * @return 检查结果
   */
  private static CheckResult checkSqliteNative() {
    try {
      Class.forName("org.sqlite.JDBC");
      try (Connection conn = DriverManager.getConnection("jdbc:sqlite::memory:")) {
        String dbVersion = conn.getMetaData().getDatabaseProductVersion();
        return new CheckResult("SQLite native library", true, "SQLite " + dbVersion);
      }
    } catch (ClassNotFoundException e) {
      return new CheckResult("SQLite native library", false, "SQLite JDBC 驱动未找到");
    } catch (SQLException e) {
      return new CheckResult("SQLite native library", false, "SQLite 连接失败: " + e.getMessage());
    }
  }

  /**
   * 检查数据目录存在性和写权限。
   *
   * <p>目录不存在时报告为警告（首次运行时正常）；目录存在但不可写时报为失败。
   *
   * @param indexDir 索引目录
   * @return 检查结果
   */
  private static CheckResult checkDataDirectory(Path indexDir) {
    String detail = indexDir.toAbsolutePath().toString();

    if (!Files.exists(indexDir)) {
      return new CheckResult("数据目录", true, detail + "（不存在，首次运行时将创建）");
    }
    if (!Files.isDirectory(indexDir)) {
      return new CheckResult("数据目录", false, detail + " 不是目录");
    }
    if (!Files.isWritable(indexDir)) {
      return new CheckResult("数据目录", false, detail + " 不可写");
    }
    return new CheckResult("数据目录", true, detail);
  }

  /**
   * 检查数据库文件完整性和可读性。
   *
   * <p>数据库不存在时报告为通过（首次运行时将创建）； 存在时通过 JDBC 连接验证 schema 版本可读。
   *
   * @param indexDir 索引目录
   * @return 检查结果
   */
  private static CheckResult checkDatabase(Path indexDir) {
    Path dbPath = indexDir.resolve(RuntimePaths.DB_FILE_NAME);

    if (!Files.exists(dbPath)) {
      return new CheckResult("数据库", true, "不存在（首次运行时将创建）");
    }

    try (Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath.toAbsolutePath());
        var stmt = conn.createStatement();
        var rs = stmt.executeQuery("SELECT sqlite_version()")) {
      if (rs.next()) {
        return new CheckResult(
            "数据库", true, dbPath.getFileName() + " 可读 (SQLite " + rs.getString(1) + ")");
      }
      return new CheckResult("数据库", true, dbPath.getFileName() + " 存在且可连接");
    } catch (SQLException e) {
      LOG.debug("数据库检查失败", e);
      return new CheckResult("数据库", false, "读取失败: " + e.getMessage());
    }
  }

  /**
   * 检查默认端口可用性。
   *
   * <p>通过 TCP 连接探测判断端口是否已被占用。端口被占用时报告为失败。
   *
   * @return 检查结果
   */
  private CheckResult checkPortAvailability() {
    if (port <= 0 || port > 65535) {
      return new CheckResult("端口 " + port, false, "端口号无效");
    }

    try (Socket socket = new Socket()) {
      socket.connect(new InetSocketAddress("127.0.0.1", port), PORT_PROBE_TIMEOUT_MS);
      return new CheckResult("端口 " + port, false, "端口已被占用");
    } catch (IOException e) {
      return new CheckResult("端口 " + port, true, "端口可用");
    }
  }

  /**
   * 检查 PID 文件状态。
   *
   * <p>PID 文件不存在时报告为通过（服务未运行）； 存在时读取并验证 PID 对应的进程是否存活。
   *
   * @param indexDir 索引目录
   * @return 检查结果
   */
  private static CheckResult checkPidFile(Path indexDir) {
    try {
      PidFile.ProcessCheck check = PidFile.checkProcess(indexDir);
      if (check.meta() == null) {
        return new CheckResult("PID 文件", true, "服务未在运行");
      }

      if (!check.processAlive()) {
        return new CheckResult(
            "PID 文件", false, "PID " + check.meta().pid() + " 对应的进程不在运行（stale PID 文件）");
      }

      return new CheckResult(
          "PID 文件", true, "服务运行中 PID " + check.meta().pid() + " (端口 " + check.meta().port() + ")");
    } catch (IOException e) {
      LOG.debug("PID 文件读取失败", e);
      return new CheckResult("PID 文件", false, "读取失败: " + e.getMessage());
    }
  }

  /**
   * 从版本字符串解析主版本号。
   *
   * <p>支持 {@code 17.0.1}、{@code 1.8.0_292} 等格式。
   *
   * @param version 版本字符串
   * @return 主版本号，解析失败时返回 0
   */
  private static int parseMajorVersion(String version) {
    if (version == null || version.isEmpty()) {
      return 0;
    }
    // 处理 1.x.0_xxx 格式（Java 8 及更早）
    if (version.startsWith("1.")) {
      String rest = version.substring(2);
      int dot = rest.indexOf('.');
      try {
        return Integer.parseInt(dot > 0 ? rest.substring(0, dot) : rest.replaceAll("[^0-9].*", ""));
      } catch (NumberFormatException e) {
        return 0;
      }
    }
    // 处理 x.y.z 格式（Java 9+）
    int dot = version.indexOf('.');
    try {
      String major = dot > 0 ? version.substring(0, dot) : version.replaceAll("[^0-9].*", "");
      return Integer.parseInt(major);
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  /**
   * 单项诊断检查结果。
   *
   * @param name 检查项名称
   * @param passed 是否通过
   * @param detail 详细信息
   */
  private record CheckResult(String name, boolean passed, String detail) {}
}
