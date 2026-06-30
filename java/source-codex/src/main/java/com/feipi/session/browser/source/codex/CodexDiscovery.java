package com.feipi.session.browser.source.codex;

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

/**
 * Codex 会话发现逻辑。
 *
 * <p>遍历 Codex 数据目录结构，发现所有 {@code *.jsonl} 会话文件。 Codex 真实目录结构为：
 *
 * <pre>{@code
 * {root}/
 *   sessions/
 *     {year}/
 *       {month}/
 *         {day}/
 *           rollout-{timestamp}-{uuid}.jsonl
 *   archived_sessions/
 *     rollout-{timestamp}-{uuid}.jsonl
 * }</pre>
 *
 * <p>发现结果按路径确定性排序。
 *
 * <p>该类是不可变的，线程安全。
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 {@code ClaudeDiscovery}、{@code QoderDiscovery} 存在结构性相似（语句级
 * STATEMENT_DUPLICATE），原因：三者分别实现各 provider 的会话发现逻辑， 目录遍历和排序结构一致但目标路径和过滤规则不同。此重复是 provider
 * 隔离设计的固有特征。
 */
public final class CodexDiscovery {

  private static final Logger LOG = Logger.getLogger(CodexDiscovery.class.getName());

  private CodexDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Codex 会话文件。
   *
   * <p>优先扫描两个子目录：
   *
   * <ul>
   *   <li>{@code {root}/sessions/}：递归遍历年/月/日三层目录，发现所有 {@code *.jsonl} 文件。
   *   <li>{@code {root}/archived_sessions/}：扁平结构，直接发现所有 {@code *.jsonl} 文件。
   * </ul>
   *
   * <p>当两个目录都不存在时，回退扫描根目录的子目录（旧结构 {@code {day-dir}/{session-id}/session.jsonl}）。
   *
   * <p>跳过隐藏目录和文件。子目录不存在时优雅跳过。
   *
   * @param rootPath 源根目录路径
   * @return 按路径排序的会话文件路径列表
   */
  public static List<Path> discoverSessions(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    Path sessionsDir = rootPath.resolve(CodexConstants.SESSIONS_DIR);
    Path archivedDir = rootPath.resolve(CodexConstants.ARCHIVED_SESSION_DIR);

    boolean hasSessionsDir =
        Files.isDirectory(sessionsDir) && !SourcePathOps.isHidden(sessionsDir);
    boolean hasArchivedDir =
        Files.isDirectory(archivedDir) && !SourcePathOps.isHidden(archivedDir);

    List<Path> allSessions = new ArrayList<>();

    if (hasSessionsDir || hasArchivedDir) {
      // 新结构：扫描 sessions/ 子树
      if (hasSessionsDir) {
        collectJsonlFilesRecursive(sessionsDir, allSessions);
      }

      // 新结构：扫描 archived_sessions/ 目录（扁平结构）
      if (hasArchivedDir) {
        collectJsonlFilesFlat(archivedDir, allSessions);
      }
    } else {
      // 旧结构 fallback：根目录下没有 sessions/ 或 archived_sessions/，
      // 回退扫描子目录中的 session.jsonl
      collectLegacySessions(rootPath, allSessions);
    }

    // 全局按路径排序，保证确定性
    allSessions.sort(Comparator.comparing(Path::toString));
    return List.copyOf(allSessions);
  }

  /**
   * 递归收集目录下所有 {@code *.jsonl} 文件。
   *
   * <p>用于 {@code sessions/} 子树（年/月/日三层目录）。跳过隐藏目录和文件。
   *
   * @param dir 起始目录
   * @param collector 收集结果的列表
   */
  private static void collectJsonlFilesRecursive(Path dir, List<Path> collector) {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (SourcePathOps.isHidden(entry)) {
          continue;
        }
        if (Files.isDirectory(entry)) {
          collectJsonlFilesRecursive(entry, collector);
        } else if (Files.isRegularFile(entry) && isJsonlFile(entry)) {
          collector.add(entry);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取目录: " + dir, e);
    }
  }

  /**
   * 收集目录下直接子级中所有 {@code *.jsonl} 文件。
   *
   * <p>用于 {@code archived_sessions/} 扁平结构。跳过隐藏文件和子目录。
   *
   * @param dir 目标目录
   * @param collector 收集结果的列表
   */
  private static void collectJsonlFilesFlat(Path dir, List<Path> collector) {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (SourcePathOps.isHidden(entry)) {
          continue;
        }
        if (Files.isRegularFile(entry) && isJsonlFile(entry)) {
          collector.add(entry);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取目录: " + dir, e);
    }
  }

  /**
   * 旧结构 fallback：扫描根目录子目录中的 {@code session.jsonl} 文件。
   *
   * <p>旧目录结构为 {@code {root}/{day-dir}/{session-id}/session.jsonl}。 遍历根目录的每个子目录，递归查找 {@code
   * session.jsonl} 文件。根目录下的直接 {@code .jsonl} 文件（如 {@code session_index.jsonl}）不视为会话文件。
   *
   * @param rootDir 根目录
   * @param collector 收集结果的列表
   */
  private static void collectLegacySessions(Path rootDir, List<Path> collector) {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(rootDir)) {
      for (Path entry : stream) {
        if (SourcePathOps.isHidden(entry) || !Files.isDirectory(entry)) {
          continue;
        }
        collectLegacySessionFilesRecursive(entry, collector);
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取根目录: " + rootDir, e);
    }
  }

  /**
   * 递归查找旧结构中的 {@code session.jsonl} 文件。
   *
   * @param dir 当前目录
   * @param collector 收集结果的列表
   */
  private static void collectLegacySessionFilesRecursive(Path dir, List<Path> collector) {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (SourcePathOps.isHidden(entry)) {
          continue;
        }
        if (Files.isDirectory(entry)) {
          collectLegacySessionFilesRecursive(entry, collector);
        } else if (Files.isRegularFile(entry)
            && entry.getFileName().toString().equals(CodexConstants.SESSION_FILE)) {
          collector.add(entry);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "无法读取目录: " + dir, e);
    }
  }

  /**
   * 判断文件是否为 {@code .jsonl} 文件。
   *
   * @param path 文件路径
   * @return 是 {@code .jsonl} 文件时返回 {@code true}
   */
  private static boolean isJsonlFile(Path path) {
    String name = path.getFileName().toString();
    return name.endsWith(CodexConstants.SESSION_FILE_SUFFIX);
  }
}
