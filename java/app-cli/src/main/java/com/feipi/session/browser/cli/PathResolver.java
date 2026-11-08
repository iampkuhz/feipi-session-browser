package com.feipi.session.browser.cli;

import java.nio.file.Path;

/** Apple Silicon macOS 的索引目录解析。 */
public final class PathResolver {

  private PathResolver() {}

  /**
   * 解析索引目录，按显式参数、INDEX_DIR、当前发行版默认目录的顺序选择。
   *
   * @param explicit CLI 指定路径，null 或空白表示未指定
   * @return 解析后的索引目录
   */
  public static Path resolveDataDir(String explicit) {
    if (explicit != null && !explicit.isBlank()) {
      return Path.of(PathUtils.expandTilde(explicit));
    }
    String configured = System.getenv("INDEX_DIR");
    return configured == null || configured.isBlank()
        ? defaultDataDir()
        : Path.of(PathUtils.expandTilde(configured));
  }

  /** 当前发行版独立的默认索引目录。 */
  public static Path defaultDataDir() {
    return Path.of(
        System.getProperty("user.home"),
        "Library",
        "Application Support",
        "feipi",
        "session-browser",
        BuildInfoVersionProvider.readAppVersion());
  }
}
