package com.feipi.session.browser.source.claude;

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
 * Claude Code 会话发现逻辑。
 *
 * <p>递归遍历 Claude Code 项目目录结构，发现所有 {@code .jsonl} 会话文件。
 * 支持发现嵌套子目录中的会话，例如 {@code <session-id>/subagents/<agent-name>.jsonl}。
 * 发现结果按完整路径确定性排序。不跟随符号链接以避免循环。
 *
 * <p>该类是不可变的，线程安全。
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 {@code CodexDiscovery}、{@code QoderDiscovery} 存在结构性相似（语句级
 * STATEMENT_DUPLICATE），原因：三者分别实现各 provider 的会话发现逻辑， 目录遍历和排序结构一致但目标路径和过滤规则不同。此重复是 provider
 * 隔离设计的固有特征。
 */
public final class ClaudeDiscovery {

  private static final Logger LOG = Logger.getLogger(ClaudeDiscovery.class.getName());

  private ClaudeDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Claude Code 会话文件。
   *
   * <p>遍历目录结构：{@code rootPath -> project dirs -> session .jsonl files}。
   * 对每个项目目录执行递归遍历，发现所有层级的 {@code .jsonl} 文件。
   * 跳过隐藏目录和文件，非 {@code .jsonl} 后缀的文件。不跟随符号链接。
   * 每个项目目录最多发现 {@link ClaudeConstants#MAX_SESSIONS_PER_PROJECT} 个会话。
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
      if (SourcePathOps.isHidden(projectDir)) {
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
   * 发现所有 {@code .jsonl} 文件（例如 {@code <session-id>/subagents/<agent-name>.jsonl}）。
   * 跳过隐藏目录、隐藏文件和非普通文件。不跟随符号链接以避免循环。
   *
   * @param projectDir 项目目录
   * @return 按完整路径排序的会话文件列表，截断至 {@link ClaudeConstants#MAX_SESSIONS_PER_PROJECT}
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
            return path.getFileName().toString().endsWith(ClaudeConstants.SESSION_FILE_SUFFIX);
          })
          .forEach(sessions::add);
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法递归遍历项目目录: " + projectDir, e);
      return List.of();
    }
    sessions.sort(Comparator.comparing(Path::toString));
    // 截断到上限
    if (sessions.size() > ClaudeConstants.MAX_SESSIONS_PER_PROJECT) {
      sessions = sessions.subList(0, ClaudeConstants.MAX_SESSIONS_PER_PROJECT);
    }
    return List.copyOf(sessions);
  }
}
