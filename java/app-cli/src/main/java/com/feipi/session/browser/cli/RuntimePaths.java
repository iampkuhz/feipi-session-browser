package com.feipi.session.browser.cli;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

/**
 * 运行时目录与文件路径的 typed 容器。
 *
 * <p>将数据目录（索引、制品）、日志目录、缓存目录和 PID 文件路径集中为一个不可变对象。 所有路径在构造时解析完成，下游直接使用，不再重复解析环境变量或默认值。
 *
 * <p>校验放置：路径解析在 {@link PathResolver} 边界执行一次（CLI 参数 > 环境变量 > 默认值）。 本 record
 * 紧凑构造器只验证非空，不重复校验路径存在性或权限。 目录创建和权限检查由 {@link #ensureDirectories()} 显式触发，不在构造时自动执行。
 *
 * @param dataDir 数据根目录，包含数据库和归一化制品
 * @param logDir 日志目录
 * @param cacheDir 缓存目录
 */
public record RuntimePaths(Path dataDir, Path logDir, Path cacheDir) {

  /** 数据库文件名，位于数据目录根。 */
  public static final String DB_FILE_NAME = "index.sqlite";

  /** 归一化制品子目录相对路径。 */
  public static final String ARTIFACT_SUBDIR = "artifacts/normalized-sessions";

  /**
   * 紧凑构造器，验证路径非空。
   *
   * <p>不验证路径存在性或权限，由 {@link #ensureDirectories()} 负责创建和权限检查。
   */
  public RuntimePaths {
    Objects.requireNonNull(dataDir, "dataDir 不得为 null");
    Objects.requireNonNull(logDir, "logDir 不得为 null");
    Objects.requireNonNull(cacheDir, "cacheDir 不得为 null");
  }

  /**
   * 从数据目录构造，日志和缓存目录按平台默认规则派生。
   *
   * @param dataDir 数据根目录
   * @return 包含派生路径的 RuntimePaths 实例
   */
  public static RuntimePaths fromDataDir(Path dataDir) {
    return new RuntimePaths(
        dataDir, PathResolver.defaultLogDir(dataDir), PathResolver.defaultCacheDir(dataDir));
  }

  /**
   * 数据库文件路径。
   *
   * @return {@code {dataDir}/index.sqlite}
   */
  public Path dbPath() {
    return dataDir.resolve(DB_FILE_NAME);
  }

  /**
   * 归一化制品目录路径。
   *
   * @return {@code {dataDir}/artifacts/normalized-sessions}
   */
  public Path artifactDir() {
    return dataDir.resolve(ARTIFACT_SUBDIR);
  }

  /**
   * PID 文件路径。
   *
   * @return {@code {dataDir}/server.pid}
   */
  public Path pidFile() {
    return dataDir.resolve(PidFile.FILE_NAME);
  }

  /**
   * 创建所有运行时目录并验证数据目录可写。
   *
   * <p>目录已存在时静默成功。权限检查通过向数据目录写入临时文件验证。
   *
   * @throws IOException 目录创建失败或数据目录不可写时
   */
  public void ensureDirectories() throws IOException {
    Files.createDirectories(dataDir);
    Files.createDirectories(logDir);
    Files.createDirectories(cacheDir);
    Files.createDirectories(artifactDir());

    Path probe = dataDir.resolve(".write-probe");
    try {
      Files.writeString(probe, "");
      Files.deleteIfExists(probe);
    } catch (IOException e) {
      throw new IOException("数据目录不可写: " + dataDir + " (" + e.getMessage() + ")", e);
    }
  }
}
