package com.feipi.session.browser.index.sqlite;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * SQLite native library 诊断工具。
 *
 * <p>提供平台检测和 native library 加载验证，支持跨平台发行诊断。 检测当前 OS/架构，验证 Xerial SQLite JDBC native library 是否可用，
 * 并确认目标平台（Mac aarch64/x86_64、Linux x86_64/aarch64、Windows x86_64）的 native library 资源均存在。
 *
 * <p>校验位于诊断边界：本类只读取 JVM 系统属性和 classpath 资源，不创建数据库连接。 运行时 native library 加载由 Xerial SQLite JDBC
 * 内部处理，本类仅验证可用性。
 */
public final class NativeLibraryDiagnostics {

  /** 四个目标平台及其在 SQLite JDBC jar 中的 native library 路径。 */
  private static final Map<String, String> TARGET_PLATFORMS;

  static {
    Map<String, String> platforms = new LinkedHashMap<>();
    platforms.put("Mac-aarch64", "org/sqlite/native/Mac/aarch64/libsqlitejdbc.dylib");
    platforms.put("Mac-x86_64", "org/sqlite/native/Mac/x86_64/libsqlitejdbc.dylib");
    platforms.put("Linux-x86_64", "org/sqlite/native/Linux/x86_64/libsqlitejdbc.so");
    platforms.put("Linux-aarch64", "org/sqlite/native/Linux/aarch64/libsqlitejdbc.so");
    TARGET_PLATFORMS = Map.copyOf(platforms);
  }

  private static final String DETECTED_OS = detectOsName();
  private static final String DETECTED_ARCH =
      normalizeArchitecture(System.getProperty("os.arch", "unknown"));

  private NativeLibraryDiagnostics() {}

  /**
   * 检测当前平台信息。
   *
   * @return 平台检测结果，包含操作系统、架构和目标平台支持状态
   */
  public static PlatformDetectionResult detect() {
    boolean supported = TARGET_PLATFORMS.containsKey(currentPlatformKey());
    return new PlatformDetectionResult(DETECTED_OS, DETECTED_ARCH, supported);
  }

  /**
   * 验证当前平台 native library 可加载。
   *
   * <p>通过打开一个 SQLite 内存连接触发 Xerial native library 提取和加载。 加载成功后连接立即关闭。
   *
   * @return 加载验证结果
   */
  public static NativeLoadResult verifyNativeLoad() {
    try {
      Class.forName("org.sqlite.JDBC");
      var conn = java.sql.DriverManager.getConnection("jdbc:sqlite::memory:");
      try {
        return new NativeLoadResult(true, currentPlatformKey(), null);
      } finally {
        conn.close();
      }
    } catch (Exception e) {
      return new NativeLoadResult(false, currentPlatformKey(), e.getMessage());
    }
  }

  /**
   * 验证四个目标平台 native library 资源均存在。
   *
   * <p>检查 SQLite JDBC jar 中是否包含 Mac aarch64/x86_64、Linux x86_64/aarch64 和 Windows x86_64 的 native
   * library。缺失任何一项时结果标记为失败。
   *
   * @return 可用性验证结果，包含缺失平台清单
   */
  public static NativeAvailabilityResult verifyAllTargetPlatforms() {
    var missing = new java.util.ArrayList<String>();
    ClassLoader cl = NativeLibraryDiagnostics.class.getClassLoader();
    for (var entry : TARGET_PLATFORMS.entrySet()) {
      if (cl.getResource(entry.getValue()) == null) {
        missing.add(entry.getKey());
      }
    }
    return new NativeAvailabilityResult(
        List.copyOf(missing), TARGET_PLATFORMS.size() - missing.size());
  }

  /**
   * 获取当前平台标识符。
   *
   * <p>格式为 {@code "OS-arch"}，例如 {@code "Mac-aarch64"} 或 {@code "Linux-x86_64"}。 不在目标平台列表中时返回 {@code
   * "OS-arch(unsupported)"}。
   *
   * @return 当前平台标识符
   */
  public static String currentPlatformKey() {
    String key = DETECTED_OS + "-" + DETECTED_ARCH;
    return TARGET_PLATFORMS.containsKey(key) ? key : key + "(unsupported)";
  }

  /**
   * 获取四个目标平台标识符。
   *
   * @return 不可变的目标平台列表
   */
  public static List<String> targetPlatformKeys() {
    return List.copyOf(TARGET_PLATFORMS.keySet());
  }

  /**
   * 配置 Xerial SQLite JDBC native library 提取目录。
   *
   * <p>设置 {@code org.sqlite.tmpdir} 系统属性，避免 native library 提取到系统临时目录。 必须在首次 SQLite JDBC
   * 连接前调用。已设置时不覆盖（命令行 {@code -D} 参数优先）。
   *
   * <p>典型调用时机：应用启动入口（CLI main），在任何数据库操作之前。
   */
  public static void configureNativeExtractionDir() {
    if (System.getProperty("org.sqlite.tmpdir") == null) {
      String userHome = System.getProperty("user.home", ".");
      System.setProperty("org.sqlite.tmpdir", userHome + "/.feipi-session-browser/native");
    }
  }

  private static String detectOsName() {
    String osName = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
    if (osName.contains("mac") || osName.contains("darwin")) {
      return "Mac";
    } else if (osName.contains("linux")) {
      return "Linux";
    } else if (osName.contains("win")) {
      return "Windows";
    } else if (osName.contains("freebsd")) {
      return "FreeBSD";
    }
    return osName.isEmpty() ? "unknown" : osName;
  }

  private static String normalizeArchitecture(String osArch) {
    return switch (osArch.toLowerCase(Locale.ROOT)) {
      case "aarch64", "arm64" -> "aarch64";
      case "amd64", "x86_64" -> "x86_64";
      case "x86", "i386", "i686" -> "x86";
      default -> osArch;
    };
  }

  /**
   * 平台检测结果。
   *
   * @param operatingSystem 操作系统名称，例如 Mac、Linux、Windows
   * @param architecture 归一化后的架构名称，例如 aarch64、x86_64
   * @param supportedTarget 当前平台是否在四个目标平台中
   */
  public record PlatformDetectionResult(
      String operatingSystem, String architecture, boolean supportedTarget) {}

  /**
   * Native library 加载验证结果。
   *
   * @param loadSuccess 加载是否成功
   * @param platform 尝试加载的平台标识符
   * @param errorMessage 失败时的错误信息，成功时为 null
   */
  public record NativeLoadResult(boolean loadSuccess, String platform, String errorMessage) {}

  /**
   * 目标平台 native library 可用性结果。
   *
   * @param missingPlatforms 缺失 native library 的目标平台列表
   * @param availableCount 可用的目标平台数量
   */
  public record NativeAvailabilityResult(List<String> missingPlatforms, int availableCount) {

    /** 所有目标平台 native library 均可用时返回 true。 */
    public boolean allPresent() {
      return missingPlatforms.isEmpty();
    }
  }
}
