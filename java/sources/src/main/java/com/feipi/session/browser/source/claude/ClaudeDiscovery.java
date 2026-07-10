package com.feipi.session.browser.source.claude;

import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import java.io.IOException;
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
 * <p>从 {@code history.jsonl} 驱动发现：读取并去重后，按 sessionId 定位 transcript 文件。 transcript
 * 缺失的会话仍然作为候选项保留（零值指纹）， 由 scan engine 负责 fallback 入库。
 *
 * <p>该类是不可变的，线程安全。
 */
public final class ClaudeDiscovery {

  private static final Logger LOG = Logger.getLogger(ClaudeDiscovery.class.getName());

  private ClaudeDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Claude Code 会话候选路径。
   *
   * <p>读取 {@code rootPath/history.jsonl}，去重后对每个 session 定位 {@code
   * projects/<project>/<sessionId>.jsonl}。 文件存在时返回真实路径；不存在时也返回路径对象（调用方通过 {@link
   * #hasTranscript(Path)} 判断）。
   *
   * @param rootPath 源根目录路径（通常为 {@code ~/.claude}）
   * @return 按 sessionId 排序的会话文件路径列表（包含缺失的 transcript 路径）
   */
  public static List<Path> discoverSessions(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    List<ClaudeHistoryEntry> history = ClaudeHistoryReader.readHistory(rootPath);
    if (history.isEmpty()) {
      return List.of();
    }

    Path projectsDir = rootPath.resolve(ClaudeConstants.PROJECTS_DIR);
    List<Path> allSessions = new ArrayList<>(history.size());

    for (ClaudeHistoryEntry entry : history) {
      Path transcriptFile = locateTranscript(projectsDir, entry);
      allSessions.add(transcriptFile);
    }

    // 按路径排序，保证确定性
    allSessions.sort(Comparator.comparing(Path::toString));
    return List.copyOf(allSessions);
  }

  /**
   * 从根目录发现所有 Claude Code 会话候选，包含 history 元数据。
   *
   * <p>与 {@link #discoverSessions(Path)} 类似，但同时返回每个会话对应的 history 条目， 供调用方构建 Candidate 时附加元数据。
   *
   * @param rootPath 源根目录路径
   * @return 按 sessionId 排序的会话发现结果列表
   */
  public static List<ClaudeSessionDiscovery> discoverSessionsWithHistory(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    List<ClaudeHistoryEntry> history = ClaudeHistoryReader.readHistory(rootPath);
    if (history.isEmpty()) {
      return List.of();
    }

    Path projectsDir = rootPath.resolve(ClaudeConstants.PROJECTS_DIR);
    List<ClaudeSessionDiscovery> results = new ArrayList<>(history.size());

    for (ClaudeHistoryEntry entry : history) {
      Path transcriptFile = locateTranscript(projectsDir, entry);
      boolean hasFile = Files.isRegularFile(transcriptFile);
      results.add(new ClaudeSessionDiscovery(entry, transcriptFile, hasFile));
    }

    // 按 sessionId 排序，保证确定性
    results.sort(Comparator.comparing(d -> d.entry().sessionId()));
    return List.copyOf(results);
  }

  /**
   * 定位 transcript 文件路径。
   *
   * <p>先在 projects/{project}/ 下查找，再搜索所有项目目录（兼容 continuation 场景）。
   */
  private static Path locateTranscript(Path projectsDir, ClaudeHistoryEntry entry) {
    if (!Files.isDirectory(projectsDir)) {
      // projects/ 目录不存在，返回合成路径
      return projectsDir.resolve(entry.project()).resolve(entry.sessionId() + ".jsonl");
    }

    // 优先在记录的项目目录下查找
    Path candidate = projectsDir.resolve(entry.project()).resolve(entry.sessionId() + ".jsonl");
    if (Files.isRegularFile(candidate)) {
      return candidate;
    }

    // 搜索所有项目目录（兼容会话在多个 project 中出现）
    try (var stream = Files.list(projectsDir)) {
      for (Path projectDir : stream.filter(Files::isDirectory).sorted().toList()) {
        Path found = projectDir.resolve(entry.sessionId() + ".jsonl");
        if (Files.isRegularFile(found)) {
          return found;
        }
        // 检查子目录（subagent 文件）
        Path subagentFound = findInSubdirs(projectDir, entry.sessionId() + ".jsonl");
        if (subagentFound != null) {
          return subagentFound;
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "搜索 transcript 文件失败: " + projectsDir, e);
    }

    // 文件不存在，返回合成路径（用于 zero-value 指纹）
    return candidate;
  }

  /** 在子目录中递归查找指定文件名的第一个匹配。 */
  private static Path findInSubdirs(Path dir, String fileName) {
    try (var walk = Files.walk(dir, 3)) {
      return walk.filter(
              p ->
                  !p.equals(dir)
                      && Files.isRegularFile(p)
                      && p.getFileName().toString().equals(fileName))
          .findFirst()
          .orElse(null);
    } catch (IOException e) {
      LOG.log(Level.FINEST, "子目录搜索失败: " + dir, e);
      return null;
    }
  }

  /**
   * 判断路径是否为实际存在的 transcript 文件。
   *
   * @param path transcript 文件路径
   * @return 文件存在时返回 {@code true}
   */
  public static boolean hasTranscript(Path path) {
    return Files.isRegularFile(path);
  }

  /**
   * Claude 会话发现结果，包含 history 元数据和 transcript 文件信息。
   *
   * @param entry history.jsonl 中的去重条目
   * @param transcriptPath transcript 文件路径（可能不存在）
   * @param hasFile transcript 文件是否实际存在
   */
  public record ClaudeSessionDiscovery(
      /* history.jsonl 中的去重条目 */
      @NotNull ClaudeHistoryEntry entry,
      /* transcript 文件路径（可能不存在） */
      @NotNull Path transcriptPath,
      /* transcript 文件是否实际存在 */
      boolean hasFile) {
    /** 校验 Claude 会话发现结果参数。 */
    public ClaudeSessionDiscovery {
      ValidationSupport.validateCanonicalConstructor(
          ClaudeSessionDiscovery.class, entry, transcriptPath, hasFile);
    }
  }
}
