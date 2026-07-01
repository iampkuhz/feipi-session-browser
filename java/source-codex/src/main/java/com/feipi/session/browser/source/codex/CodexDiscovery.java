package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.source.spi.SourcePathOps;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Codex 会话发现逻辑。
 *
 * <p>从 {@code state_5.sqlite} threads 表和 {@code session_index.jsonl} 驱动发现。 排除 subagent thread，rollout 文件仅作为定位/解析来源。
 *
 * <p>发现策略与 Python master 对齐：
 *
 * <ol>
 *   <li>读 threads.db → 过滤 subagent → 得到 top-level threads 列表
 *   <li>读 session_index.jsonl → 补充 threads.db 中没有的条目
 *   <li>对每个 top-level session，定位 rollout 文件
 * </ol>
 *
 * <p>该类是不可变的，线程安全。
 */
public final class CodexDiscovery {

  private static final Logger LOG = Logger.getLogger(CodexDiscovery.class.getName());

  private CodexDiscovery() {
    // 工具类，禁止实例化
  }

  /**
   * 从根目录发现所有 Codex 顶层会话候选路径。
   *
   * <p>使用 threads.db + session_index.jsonl 驱动，排除 subagent thread。 返回的每个路径都对应一个顶层会话的 rollout 文件（可能不存在）。
   *
   * @param rootPath 源根目录路径
   * @return 按 sessionId 排序的会话发现结果列表
   */
  public static List<CodexSessionDiscovery> discoverSessionsWithMetadata(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    // 第一步：读 threads.db
    Path threadsDbPath = rootPath.resolve(CodexConstants.THREADS_DB);
    List<Map<String, String>> allThreads = ThreadsDbReader.readThreads(threadsDbPath);

    // 第二步：过滤 subagent threads，保留顶层
    Map<String, Map<String, String>> topLevelThreads = new LinkedHashMap<>();
    for (Map<String, String> thread : allThreads) {
      String id = thread.getOrDefault("id", "");
      if (id.isEmpty()) {
        continue;
      }
      if (!isSubagentThread(thread)) {
        topLevelThreads.put(id, thread);
      }
    }

    // 第三步：读取会话索引，补充缺失条目
    Map<String, Map<String, String>> indexEntries = readSessionIndex(rootPath);
    Set<String> allSessionIds = new LinkedHashSet<>(topLevelThreads.keySet());
    for (String id : indexEntries.keySet()) {
      if (!topLevelThreads.containsKey(id)) {
        allSessionIds.add(id);
      }
    }

    // 第四步：对每个会话定位 rollout 文件
    List<CodexSessionDiscovery> results = new ArrayList<>();
    for (String sessionId : allSessionIds) {
      Map<String, String> threadInfo = topLevelThreads.get(sessionId);
      Map<String, String> indexEntry = indexEntries.get(sessionId);

      Path rolloutFile = locateRolloutFile(rootPath, sessionId, threadInfo);
      boolean hasFile = Files.isRegularFile(rolloutFile);

      results.add(
          new CodexSessionDiscovery(
              sessionId,
              threadInfo,
              indexEntry,
              rolloutFile,
              hasFile));
    }

    // 按 sessionId 排序，保证确定性
    results.sort(Comparator.comparing(CodexSessionDiscovery::sessionId));
    return List.copyOf(results);
  }

  /**
   * 从根目录发现所有 Codex 顶层会话候选路径（简化 API）。
   *
   * @param rootPath 源根目录路径
   * @return 按 sessionId 排序的 rollout 文件路径列表
   */
  public static List<Path> discoverSessions(Path rootPath) {
    return discoverSessionsWithMetadata(rootPath).stream()
        .map(CodexSessionDiscovery::rolloutPath)
        .toList();
  }

  /**
   * 判断 thread 信息是否表示 subagent。
   *
   * <p>与 Python {@code is_codex_subagent_thread_info} 对齐：
   *
   * <ul>
   *   <li>{@code thread_source} 为 "subagent"
   *   <li>{@code parent_thread_id} 非空
   *   <li>{@code source.subagent.thread_spawn.parent_thread_id} 非空
   * </ul>
   */
  static boolean isSubagentThread(Map<String, String> threadInfo) {
    if (threadInfo == null) {
      return false;
    }

    String threadSource = threadInfo.getOrDefault("thread_source", "").trim();
    if ("subagent".equalsIgnoreCase(threadSource)) {
      return true;
    }

    String parentId = threadInfo.getOrDefault("parent_thread_id", "").trim();
    if (!parentId.isEmpty()) {
      return true;
    }

    // 检查嵌套 source.subagent.thread_spawn.parent_thread_id
    String sourceJson = threadInfo.get("source");
    if (sourceJson != null && !sourceJson.isEmpty()) {
      try {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode sourceNode = mapper.readTree(sourceJson);
        if (sourceNode.isObject()) {
          JsonNode subagent = sourceNode.get("subagent");
          if (subagent != null && subagent.isObject()) {
            JsonNode spawn = subagent.get("thread_spawn");
            if (spawn != null && spawn.isObject()) {
              JsonNode spawnParent = spawn.get("parent_thread_id");
              if (spawnParent != null
                  && spawnParent.isTextual()
                  && !spawnParent.asText().trim().isEmpty()) {
                return true;
              }
            }
          }
        }
      } catch (IOException e) {
        LOG.log(Level.FINEST, "source 字段解析失败", e);
      }
    }

    return false;
  }

  /** 读取会话索引文件。 */
  private static Map<String, Map<String, String>> readSessionIndex(Path rootPath) {
    Path indexPath = rootPath.resolve(CodexConstants.SESSION_INDEX_FILE);
    if (!Files.isRegularFile(indexPath)) {
      return Map.of();
    }

    Map<String, Map<String, String>> entries = new LinkedHashMap<>();
    ObjectMapper mapper = new ObjectMapper();

    try (BufferedReader reader = Files.newBufferedReader(indexPath, StandardCharsets.UTF_8)) {
      String line;
      while ((line = reader.readLine()) != null) {
        String trimmed = line.trim();
        if (trimmed.isEmpty()) {
          continue;
        }
        try {
          JsonNode node = mapper.readTree(trimmed);
          if (!node.isObject()) {
            continue;
          }
          String id = textOrEmpty(node, "id");
          if (id.isEmpty()) {
            continue;
          }
          Map<String, String> entry = new LinkedHashMap<>();
          entry.put("id", id);
          entry.put("thread_name", textOrEmpty(node, "thread_name"));
          entry.put("updated_at", textOrEmpty(node, "updated_at"));
          entries.put(id, entry);
        } catch (IOException e) {
          LOG.log(Level.FINE, "跳过无法解析的 session_index.jsonl 行", e);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "读取 session_index.jsonl 失败: " + indexPath, e);
      return Map.of();
    }

    return entries;
  }

  private static String textOrEmpty(JsonNode node, String field) {
    JsonNode child = node.get(field);
    if (child != null && child.isTextual()) {
      return child.asText();
    }
    return "";
  }

  /**
   * 定位 rollout 文件路径。
   *
   * <p>优先使用 threads.db 中的 rollout_path，否则在 sessions/ 目录树中搜索。
   */
  private static Path locateRolloutFile(
      Path rootPath, String sessionId, Map<String, String> threadInfo) {
    // 优先使用 threads.db 中的 rollout_path
    if (threadInfo != null) {
      String rolloutPath = threadInfo.getOrDefault("rollout_path", "");
      if (!rolloutPath.isEmpty()) {
        Path p = Path.of(rolloutPath);
        if (Files.isRegularFile(p)) {
          return p;
        }
      }
    }

    // 在 sessions/ 目录树中搜索
    Path sessionsDir = rootPath.resolve(CodexConstants.SESSIONS_DIR);
    if (Files.isDirectory(sessionsDir)) {
      Path found = searchRolloutInDir(sessionsDir, sessionId);
      if (found != null) {
        return found;
      }
    }

    // 在 archived_sessions/ 目录中搜索
    Path archivedDir = rootPath.resolve(CodexConstants.ARCHIVED_SESSION_DIR);
    if (Files.isDirectory(archivedDir)) {
      Path found = searchRolloutInFlatDir(archivedDir, sessionId);
      if (found != null) {
        return found;
      }
    }

    // 文件不存在，返回合成路径
    String globPattern = "rollout-*-" + sessionId + ".jsonl";
    if (Files.isDirectory(sessionsDir)) {
      return sessionsDir.resolve("0000/00/00").resolve(globPattern);
    }
    return rootPath.resolve("sessions").resolve(globPattern);
  }

  /** 在 sessions/ 子树中搜索 rollout 文件。 */
  private static Path searchRolloutInDir(Path dir, String sessionId) {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (SourcePathOps.isHidden(entry)) {
          continue;
        }
        if (Files.isDirectory(entry)) {
          Path found = searchRolloutInDir(entry, sessionId);
          if (found != null) {
            return found;
          }
        } else if (Files.isRegularFile(entry)) {
          String name = entry.getFileName().toString();
          if (name.endsWith(".jsonl") && name.contains(sessionId)) {
            return entry;
          }
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "搜索 rollout 文件失败: " + dir, e);
    }
    return null;
  }

  /** 在 archived_sessions/ 扁平目录中搜索 rollout 文件。 */
  private static Path searchRolloutInFlatDir(Path dir, String sessionId) {
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
      for (Path entry : stream) {
        if (SourcePathOps.isHidden(entry)) {
          continue;
        }
        if (Files.isRegularFile(entry)) {
          String name = entry.getFileName().toString();
          if (name.endsWith(".jsonl") && name.contains(sessionId)) {
            return entry;
          }
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINE, "搜索 archived rollout 文件失败: " + dir, e);
    }
    return null;
  }

  /**
   * Codex 会话发现结果，包含 threads.db 元数据和 rollout 文件信息。
   *
   * @param sessionId 会话 UUID
   * @param threadInfo threads.db 中的线程信息，不存在时为 null
   * @param indexEntry session_index.jsonl 中的条目，不存在时为 null
   * @param rolloutPath rollout 文件路径（可能不存在）
   * @param hasFile rollout 文件是否实际存在
   */
  public record CodexSessionDiscovery(
      String sessionId,
      Map<String, String> threadInfo,
      Map<String, String> indexEntry,
      Path rolloutPath,
      boolean hasFile) {}
}
