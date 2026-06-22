package com.feipi.session.browser.source.claude;

import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Claude Code 会话发现逻辑。
 *
 * <p>遍历 Claude Code 项目目录结构，发现所有 {@code .jsonl} 会话文件。 发现结果按路径确定性排序：先按项目目录名排序，再按会话文件名排序。
 *
 * <p>该类是不可变的，线程安全。
 */
public final class ClaudeDiscovery {

  private static final Logger LOG = Logger.getLogger(ClaudeDiscovery.class.getName());

  private ClaudeDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Claude Code 会话文件。
   *
   * <p>遍历目录结构：{@code rootPath -> project dirs -> session .jsonl files}。 跳过隐藏目录和文件，非 {@code .jsonl}
   * 后缀的文件。 每个项目目录最多发现 {@link ClaudeConstants#MAX_SESSIONS_PER_PROJECT} 个会话。
   *
   * @param rootPath 源根目录路径（通常为 {@code ~/.claude}）
   * @return 按路径排序的会话文件路径列表
   */
  public static List<Path> discoverSessions(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    Path projectsDir = rootPath.resolve(ClaudeConstants.PROJECTS_DIR);
    if (!Files.isDirectory(projectsDir)) {
      return List.of();
    }

    List<Path> allSessions = new ArrayList<>();

    List<Path> projectDirs = listSortedDirectories(projectsDir);
    for (Path projectDir : projectDirs) {
      if (isHidden(projectDir)) {
        continue;
      }
      List<Path> sessionFiles = listSortedSessions(projectDir);
      allSessions.addAll(sessionFiles);
    }

    // 全局按路径排序，保证确定性
    allSessions.sort(Comparator.comparing(Path::toString));
    return List.copyOf(allSessions);
  }

  /**
   * 列出目录中的子目录，按名称排序。
   *
   * @param dir 父目录
   * @return 排序后的子目录列表
   */
  private static List<Path> listSortedDirectories(Path dir) {
    List<Path> dirs = new ArrayList<>();
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (Files.isDirectory(entry) && !isHidden(entry)) {
          dirs.add(entry);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取目录: " + dir, e);
      return List.of();
    }
    dirs.sort(Comparator.comparing(p -> p.getFileName().toString()));
    return List.copyOf(dirs);
  }

  /**
   * 列出项目目录中的会话 JSONL 文件，按文件名排序。
   *
   * @param projectDir 项目目录
   * @return 排序后的会话文件列表
   */
  private static List<Path> listSortedSessions(Path projectDir) {
    List<Path> sessions = new ArrayList<>();
    try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(projectDir, "*" + ClaudeConstants.SESSION_FILE_SUFFIX)) {
      for (Path entry : stream) {
        if (Files.isRegularFile(entry) && !isHidden(entry)) {
          sessions.add(entry);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取项目目录: " + projectDir, e);
      return List.of();
    }
    sessions.sort(Comparator.comparing(p -> p.getFileName().toString()));
    // 截断到上限
    if (sessions.size() > ClaudeConstants.MAX_SESSIONS_PER_PROJECT) {
      sessions = sessions.subList(0, ClaudeConstants.MAX_SESSIONS_PER_PROJECT);
    }
    return List.copyOf(sessions);
  }

  /**
   * 判断路径是否为隐藏文件/目录（名称以 {@code .} 开头）。
   *
   * @param path 待检查路径
   * @return 隐藏时返回 {@code true}
   */
  private static boolean isHidden(Path path) {
    String name = path.getFileName().toString();
    return name.startsWith(".");
  }
}
