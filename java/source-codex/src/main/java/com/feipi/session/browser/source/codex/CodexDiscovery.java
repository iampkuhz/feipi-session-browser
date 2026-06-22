package com.feipi.session.browser.source.codex;

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
 * Codex 会话发现逻辑。
 *
 * <p>遍历 Codex 数据目录结构，发现所有 {@code session.jsonl} 会话文件。 Codex 目录结构为 {@code
 * {root}/{日期目录}/{session-id}/session.jsonl}。
 *
 * <p>发现结果按路径确定性排序：先按日期目录名排序，再按 session id 排序。
 *
 * <p>该类是不可变的，线程安全。
 */
public final class CodexDiscovery {

  private static final Logger LOG = Logger.getLogger(CodexDiscovery.class.getName());

  private CodexDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Codex 会话文件。
   *
   * <p>遍历目录结构：{@code rootPath -> 日期目录 -> 会话目录 -> session.jsonl}。 跳过隐藏目录和文件。 每个日期目录最多发现 {@link
   * CodexConstants#MAX_SESSIONS_PER_DAY} 个会话。
   *
   * @param rootPath 源根目录路径
   * @return 按路径排序的会话文件路径列表
   */
  public static List<Path> discoverSessions(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    List<Path> allSessions = new ArrayList<>();

    List<Path> dayDirs = listSortedDirectories(rootPath);
    for (Path dayDir : dayDirs) {
      if (isHidden(dayDir)) {
        continue;
      }
      List<Path> sessionFiles = discoverInDayDir(dayDir);
      allSessions.addAll(sessionFiles);
    }

    // 全局按路径排序，保证确定性
    allSessions.sort(Comparator.comparing(Path::toString));
    return List.copyOf(allSessions);
  }

  /**
   * 在单个日期目录中发现会话文件。
   *
   * <p>遍历日期目录下的 session 子目录，查找 {@code session.jsonl} 文件。
   *
   * @param dayDir 日期目录路径
   * @return 排序后的会话文件列表
   */
  private static List<Path> discoverInDayDir(Path dayDir) {
    List<Path> sessions = new ArrayList<>();

    List<Path> sessionDirs = listSortedDirectories(dayDir);
    for (Path sessionDir : sessionDirs) {
      if (isHidden(sessionDir)) {
        continue;
      }
      Path sessionFile = sessionDir.resolve(CodexConstants.SESSION_FILE);
      if (Files.isRegularFile(sessionFile)) {
        sessions.add(sessionFile);
      }
    }

    sessions.sort(Comparator.comparing(p -> p.getParent().getFileName().toString()));
    // 截断到上限
    if (sessions.size() > CodexConstants.MAX_SESSIONS_PER_DAY) {
      sessions = sessions.subList(0, CodexConstants.MAX_SESSIONS_PER_DAY);
    }
    return List.copyOf(sessions);
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
