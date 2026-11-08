package com.feipi.session.browser.cli;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

/**
 * 数据目录及其派生的索引、制品和 PID 路径。
 *
 * @param dataDir 数据根目录，包含数据库和归一化制品
 */
public record RuntimePaths(Path dataDir) {

  /** 数据库文件名，位于数据目录根。 */
  public static final String DB_FILE_NAME = String.join("", "index", ".sqlite");

  /** 归一化制品子目录相对路径。 */
  public static final String ARTIFACT_SUBDIR = "artifacts/normalized-sessions";

  /**
   * 紧凑构造器，验证路径非空。
   *
   * <p>不验证路径存在性或权限，由 {@link #ensureDirectories()} 负责创建和权限检查。
   */
  public RuntimePaths {
    Objects.requireNonNull(dataDir, "dataDir 不得为 null");
  }

  /**
   * 数据库文件路径。
   *
   * @return 数据目录下的默认数据库文件路径
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
