package com.feipi.session.browser.source.qoder;

import com.feipi.session.browser.source.spi.SourcePathOps;
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.stream.Stream;

/**
 * Qoder 会话发现逻辑。
 *
 * <p>递归遍历 Qoder 项目目录结构，发现所有 {@code .jsonl} 会话文件。 Qoder 有两个会话目录：
 *
 * <ul>
 *   <li>{@code {root}/projects/} — 主会话目录
 *   <li>{@code {root}/cache/projects/} — 缓存会话目录
 * </ul>
 *
 * <p>对每个项目目录执行递归遍历，支持发现任意深度嵌套的会话文件，
 * 例如 {@code cache/projects/<key>/conversation-history/<id>/<id>.jsonl}。
 * 发现结果按完整路径确定性排序。不跟随符号链接以避免循环。
 *
 * <p>该类是不可变的，线程安全。
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 {@code ClaudeDiscovery}、{@code CodexDiscovery} 存在结构性相似（语句级
 * STATEMENT_DUPLICATE），原因：三者分别实现各 provider 的会话发现逻辑， 目录遍历和排序结构一致但目标路径和过滤规则不同。此重复是 provider
 * 隔离设计的固有特征。
 */
public final class QoderDiscovery {

  private static final Logger LOG = Logger.getLogger(QoderDiscovery.class.getName());

  private QoderDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Qoder 会话文件。
   *
   * <p>遍历 {@code projects/} 和 {@code cache/projects/} 两个子树，
   * 对每个项目目录执行递归遍历，找到所有层级的 {@code .jsonl} 文件。
   * 跳过隐藏目录和文件。不跟随符号链接。
   * 全局按路径排序，保证确定性。
   *
   * @param rootPath 源根目录路径
   * @return 按路径排序的会话文件路径列表
   */
  public static List<Path> discoverSessions(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    Path projectsDir = rootPath.resolve(QoderConstants.PROJECTS_DIR);
    Path cacheProjectsDir = rootPath.resolve(QoderConstants.CACHE_PROJECTS_DIR);

    List<Path> allSessions = new ArrayList<>();

    // 遍历主 projects/ 目录
    if (Files.isDirectory(projectsDir)) {
      collectSessions(projectsDir, allSessions);
    }

    // 遍历 cache/projects/ 目录
    if (Files.isDirectory(cacheProjectsDir)) {
      collectSessions(cacheProjectsDir, allSessions);
    }

    // 全局按路径排序，保证确定性
    allSessions.sort(Comparator.comparing(Path::toString));
    return List.copyOf(allSessions);
  }

  /**
   * 从指定的项目父目录收集所有会话文件。
   *
   * <p>遍历项目父目录下的每个子目录（项目目录），对每个项目目录执行递归遍历，
   * 收集其中所有层级的 {@code .jsonl} 文件。
   *
   * @param projectsParentDir 项目父目录（{@code projects/} 或 {@code cache/projects/}）
   * @param accumulator 结果收集器
   */
  private static void collectSessions(Path projectsParentDir, List<Path> accumulator) {
    List<Path> projectDirs = listSortedDirectories(projectsParentDir);
    for (Path projectDir : projectDirs) {
      if (SourcePathOps.isHidden(projectDir)) {
        continue;
      }
      List<Path> sessionFiles = listSortedSessions(projectDir);
      accumulator.addAll(sessionFiles);
    }
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
        if (Files.isDirectory(entry) && !SourcePathOps.isHidden(entry)) {
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
   * 递归列出项目目录中的所有会话 JSONL 文件，按完整路径排序。
   *
   * <p>使用 {@link Files#walk} 递归遍历项目目录的任意深度子目录，
   * 发现所有 {@code .jsonl} 文件（例如 {@code conversation-history/<id>/<id>.jsonl}）。
   * 跳过隐藏目录、隐藏文件和非普通文件。不跟随符号链接以避免循环。
   *
   * @param projectDir 项目目录
   * @return 按完整路径排序的会话文件列表，截断至 {@link QoderConstants#MAX_SESSIONS_PER_PROJECT}
   */
  private static List<Path> listSortedSessions(Path projectDir) {
    List<Path> sessions = new ArrayList<>();
    try (Stream<Path> walk = Files.walk(projectDir)) {
      walk.filter(path -> !path.equals(projectDir))
          .filter(path -> {
            if (SourcePathOps.isHidden(path)) {
              return false;
            }
            if (!Files.isRegularFile(path)) {
              return false;
            }
            // 检查路径中是否存在隐藏的祖先目录
            Path relative = projectDir.relativize(path);
            for (int i = 0; i < relative.getNameCount() - 1; i++) {
              if (SourcePathOps.isHidden(projectDir.resolve(relative.subpath(0, i + 1)))) {
                return false;
              }
            }
            return path.getFileName().toString().endsWith(QoderConstants.SESSION_FILE_SUFFIX);
          })
          .forEach(sessions::add);
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法递归遍历项目目录: " + projectDir, e);
      return List.of();
    }
    sessions.sort(Comparator.comparing(Path::toString));
    // 截断到上限
    if (sessions.size() > QoderConstants.MAX_SESSIONS_PER_PROJECT) {
      sessions = sessions.subList(0, QoderConstants.MAX_SESSIONS_PER_PROJECT);
    }
    return List.copyOf(sessions);
  }
}
