package com.feipi.session.browser.cli;

import java.nio.file.Path;

/**
 * 跨平台运行时路径解析器。
 *
 * <p>遵循 XDG Base Directory 规范，根据操作系统解析数据、日志、缓存的默认目录。 配置优先级：CLI 参数 > 环境变量 > 默认值。
 *
 * <p>所有方法为纯函数或仅读取系统属性/环境变量，不写入文件系统。 路径含空格、Unicode 字符、长路径均可正确处理，因为使用 {@link Path} 而非字符串拼接。
 */
public final class PathResolver {

  /** 应用厂商标识，用于 XDG 目录组织。 */
  private static final String VENDOR = "feipi";

  /** 应用名称标识，用于 XDG 目录组织。 */
  private static final String APP = "session-browser";

  private PathResolver() {}

  /**
   * 解析索引/数据目录。
   *
   * <p>优先级：显式路径 > 环境变量值 > XDG 平台默认值。 显式路径和环境变量值均通过 {@link PathUtils#expandTilde} 展开 {@code ~}。
   *
   * @param explicit CLI 显式指定的路径，null 或空白表示未指定
   * @param envVar 环境变量名
   * @return 解析后的数据目录路径
   */
  public static Path resolveDataDir(String explicit, String envVar) {
    if (explicit != null && !explicit.isBlank()) {
      return Path.of(PathUtils.expandTilde(explicit));
    }
    String envValue = System.getenv(envVar);
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return defaultDataDir();
  }

  /**
   * 解析 agent 数据源目录。
   *
   * <p>优先级：环境变量值 > 默认路径。默认路径通常为 agent 在用户主目录下的配置目录。
   *
   * @param envVar 环境变量名
   * @param defaultPath 默认路径
   * @return 解析后的数据源目录路径
   */
  public static Path resolveSourceDataDir(String envVar, Path defaultPath) {
    String envValue = System.getenv(envVar);
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return defaultPath;
  }

  /**
   * 默认数据目录，遵循 XDG Base Directory 规范。
   *
   * <ul>
   *   <li>macOS: {@code ~/Library/Application Support/feipi/session-browser}
   *   <li>Linux: {@code ~/.local/share/feipi/session-browser}
   *   <li>Windows: {@code %LOCALAPPDATA%/feipi/session-browser}
   * </ul>
   *
   * @return 平台对应的默认数据目录
   */
  public static Path defaultDataDir() {
    String home = System.getProperty("user.home");
    String os = System.getProperty("os.name", "").toLowerCase();

    if (os.contains("mac")) {
      return Path.of(home, "Library", "Application Support", VENDOR, APP);
    }
    if (os.contains("win")) {
      String localAppData = System.getenv("LOCALAPPDATA");
      if (localAppData != null && !localAppData.isBlank()) {
        return Path.of(localAppData, VENDOR, APP);
      }
      return Path.of(home, "AppData", "Local", VENDOR, APP);
    }
    // Linux 和其他 Unix-like 系统：XDG_DATA_HOME
    return Path.of(home, ".local", "share", VENDOR, APP);
  }

  /**
   * 默认日志目录，基于数据目录派生。
   *
   * <ul>
   *   <li>macOS: {@code ~/Library/Logs/feipi/session-browser}
   *   <li>Linux: {@code dataDir/logs}
   *   <li>Windows: {@code dataDir/logs}
   * </ul>
   *
   * @param dataDir 数据目录，用于 Linux/Windows 派生
   * @return 平台对应的默认日志目录
   */
  public static Path defaultLogDir(Path dataDir) {
    String os = System.getProperty("os.name", "").toLowerCase();
    if (os.contains("mac")) {
      return Path.of(System.getProperty("user.home"), "Library", "Logs", VENDOR, APP);
    }
    return dataDir.resolve("logs");
  }

  /**
   * 默认缓存目录，基于数据目录派生。
   *
   * <ul>
   *   <li>macOS: {@code ~/Library/Caches/feipi/session-browser}
   *   <li>Linux: {@code dataDir/cache}
   *   <li>Windows: {@code dataDir/cache}
   * </ul>
   *
   * @param dataDir 数据目录，用于 Linux/Windows 派生
   * @return 平台对应的默认缓存目录
   */
  public static Path defaultCacheDir(Path dataDir) {
    String os = System.getProperty("os.name", "").toLowerCase();
    if (os.contains("mac")) {
      return Path.of(System.getProperty("user.home"), "Library", "Caches", VENDOR, APP);
    }
    return dataDir.resolve("cache");
  }
}
