package com.feipi.session.browser.cli;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.List;

/** CLI 运行时 preflight 检查共享实现。 */
final class RuntimePreflight {

  /** 产品最低 Java 主版本。 */
  private static final int MIN_JAVA_MAJOR_VERSION = 17;

  private RuntimePreflight() {}

  /** 检查 Java runtime 主版本满足产品运行要求。 */
  static CheckResult checkJavaRuntime() {
    String version = System.getProperty("java.version", "unknown");
    String vendor = System.getProperty("java.vendor", "unknown");
    String vmName = System.getProperty("java.vm.name", "unknown");
    int majorVersion = parseMajorVersion(version);
    boolean passed = majorVersion >= MIN_JAVA_MAJOR_VERSION;
    String detail = "版本 " + version + " (" + vendor + ", " + vmName + "；需要 Java 17+)";
    return new CheckResult("Java 运行时", passed, detail);
  }

  /** 检查 SQLite JDBC native library 可加载。 */
  static CheckResult checkSqliteNative() {
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

  /** 输出检查结果，并返回 CLI 退出码。 */
  static int printResults(List<CheckResult> results, String successMessage, String failurePrefix) {
    int failed = 0;
    for (CheckResult result : results) {
      String status = result.passed() ? "[OK]" : "[FAIL]";
      System.out.println(status + " " + result.name());
      if (!result.detail().isBlank()) {
        System.out.println("     " + result.detail());
      }
      if (!result.passed()) {
        failed++;
      }
    }

    System.out.println();
    if (failed == 0) {
      System.out.println(successMessage);
      return 0;
    }

    System.out.println(failurePrefix + failed + " 项检查失败。");
    return 1;
  }

  /** 解析 Java 主版本号。 */
  static int parseMajorVersion(String version) {
    if (version == null || version.isBlank()) {
      return 0;
    }
    if (version.startsWith("1.")) {
      String rest = version.substring(2);
      int dot = rest.indexOf('.');
      return parseLeadingInt(dot > 0 ? rest.substring(0, dot) : rest);
    }
    int dot = version.indexOf('.');
    return parseLeadingInt(dot > 0 ? version.substring(0, dot) : version);
  }

  /** 解析字符串开头的整数，失败返回 0。 */
  private static int parseLeadingInt(String value) {
    String digits = value.replaceAll("[^0-9].*", "");
    if (digits.isBlank()) {
      return 0;
    }
    try {
      return Integer.parseInt(digits);
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  /**
   * 检查结果数据。
   *
   * @param name 检查项名称。
   * @param passed 检查是否通过。
   * @param detail 详情文本。
   */
  record CheckResult(
      /* 检查项名称。 */
      String name,

      /* 检查是否通过。 */
      boolean passed,

      /* 详情文本。 */
      String detail) {}
}
