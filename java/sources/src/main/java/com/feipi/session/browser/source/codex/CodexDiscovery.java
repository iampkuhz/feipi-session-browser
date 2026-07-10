package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.source.codex.db.ThreadsDbReader;
import com.feipi.session.browser.source.common.JsonNodeReaders;
import com.feipi.session.browser.source.common.JsonlObjectReader;
import com.feipi.session.browser.source.spi.SourcePathOps;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
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
 * <p>从 {@code state_5.sqlite} threads 表和 {@code session_index.jsonl} 驱动发现。 排除 subagent
 * thread，rollout 文件仅作为定位/解析来源。
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
   * <p>使用 threads.db + session_index.jsonl 驱动，排除 subagent thread。 返回的每个路径都对应一个顶层会话的 rollout
   * 文件（可能不存在）。
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

    // 第四步：过滤 index-only entries 中的 subagent sessions（与 Python 对齐）
    Map<String, Map<String, String>> filteredIndexEntries = new LinkedHashMap<>();
    for (String id : indexEntries.keySet()) {
      if (!topLevelThreads.containsKey(id)) {
        // index-only entry：需要通过 rollout 文件的 session_meta 判断是否为 subagent
        Path rolloutFile = locateRolloutFile(rootPath, id, null);
        if (isSubagentRolloutFile(rolloutFile)) {
          LOG.log(Level.FINE, "跳过 index-only subagent session: {0}", id);
          continue;
        }
      }
      filteredIndexEntries.put(id, indexEntries.get(id));
    }

    // 第五步：对每个会话定位 rollout 文件
    List<CodexSessionDiscovery> results = new ArrayList<>();
    for (String sessionId : allSessionIds) {
      if (!filteredIndexEntries.containsKey(sessionId) && !topLevelThreads.containsKey(sessionId)) {
        // 被 subagent 过滤掉的 index-only entry
        continue;
      }
      Map<String, String> threadInfo = topLevelThreads.get(sessionId);
      Map<String, String> indexEntry = filteredIndexEntries.get(sessionId);

      Path rolloutFile = locateRolloutFile(rootPath, sessionId, threadInfo);
      boolean hasFile = Files.isRegularFile(rolloutFile);

      results.add(
          new CodexSessionDiscovery(sessionId, threadInfo, indexEntry, rolloutFile, hasFile));
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
    return hasNestedSubagentParent(threadInfo.get("source"), "source 字段解析失败");
  }

  private static boolean hasNestedSubagentParent(String sourceJson, String parseErrorMessage) {
    if (sourceJson == null || sourceJson.isEmpty()) {
      return false;
    }
    try {
      ObjectMapper mapper = new ObjectMapper();
      JsonNode sourceNode = mapper.readTree(sourceJson);
      if (!sourceNode.isObject()) {
        return false;
      }
      JsonNode subagent = sourceNode.get("subagent");
      if (subagent == null || !subagent.isObject()) {
        return false;
      }
      JsonNode spawn = subagent.get("thread_spawn");
      if (spawn == null || !spawn.isObject()) {
        return false;
      }
      JsonNode spawnParent = spawn.get("parent_thread_id");
      return spawnParent != null
          && spawnParent.isTextual()
          && !spawnParent.asText().trim().isEmpty();
    } catch (IOException e) {
      LOG.log(Level.FINEST, parseErrorMessage, e);
      return false;
    }
  }

  /** 读取会话索引文件。 */
  private static Map<String, Map<String, String>> readSessionIndex(Path rootPath) {
    Path indexPath = rootPath.resolve(CodexConstants.SESSION_INDEX_FILE);
    if (!Files.isRegularFile(indexPath)) {
      return Map.of();
    }

    Map<String, Map<String, String>> entries = new LinkedHashMap<>();
    for (JsonNode node :
        JsonlObjectReader.readObjects(
            indexPath, LOG, "跳过无法解析的 session_index.jsonl 行", "读取 session_index.jsonl 失败: ")) {
      String id = JsonNodeReaders.textOrEmpty(node, "id");
      if (id.isEmpty()) {
        continue;
      }
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("id", id);
      entry.put("thread_name", JsonNodeReaders.textOrEmpty(node, "thread_name"));
      entry.put("updated_at", JsonNodeReaders.textOrEmpty(node, "updated_at"));
      String model = JsonNodeReaders.textOrEmpty(node, "model");
      if (!model.isEmpty()) {
        entry.put("model", model);
      }
      entries.put(id, entry);
    }

    return entries;
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
   * 检查 rollout 文件的 session_meta 事件是否表示 subagent 会话。
   *
   * <p>与 Python {@code is_codex_subagent_session_file} 对齐：读取文件首行， 若为 {@code session_meta} 事件则委托
   * {@link #isSubagentMetaEvent} 判断。 文件不存在或解析失败时返回 {@code false}。
   *
   * @param rolloutFile rollout 文件路径
   * @return 识别为 subagent 时返回 {@code true}
   */
  static boolean isSubagentRolloutFile(Path rolloutFile) {
    if (rolloutFile == null || !Files.isRegularFile(rolloutFile)) {
      return false;
    }
    Map<String, String> meta = readFirstEventAsMap(rolloutFile);
    if (meta == null || !"session_meta".equals(meta.get("type"))) {
      return false;
    }
    return isSubagentMetaEvent(meta);
  }

  /**
   * 判断 session_meta 事件字段是否表示 subagent。
   *
   * <p>检测条件与 Python {@code is_codex_subagent_session_meta} 对齐：
   *
   * <ul>
   *   <li>{@code thread_source} 为 "subagent"
   *   <li>{@code parent_thread_id} 非空
   *   <li>{@code source.subagent.thread_spawn.parent_thread_id} 非空
   * </ul>
   */
  static boolean isSubagentMetaEvent(Map<String, String> meta) {
    if (meta == null) {
      return false;
    }
    String threadSource = meta.getOrDefault("thread_source", "");
    if ("subagent".equalsIgnoreCase(threadSource.trim())) {
      return true;
    }
    String parentId = meta.getOrDefault("parent_thread_id", "").trim();
    if (!parentId.isEmpty()) {
      return true;
    }
    return hasNestedSubagentParent(meta.get("source"), "session_meta.source 解析失败");
  }

  /**
   * 将 JSON 节点的 payload 字段扁平化为字符串映射。
   *
   * <p>对 {@code payload} 内的文本、数字、布尔值字段做扁平化处理， 嵌套结构序列化为 JSON 字符串保留。 供 {@link
   * CodexSourceAdapter#extractSessionMeta} 等方法复用，避免重复实现。
   *
   * @param event JSON 事件节点
   * @return payload 字段映射；payload 不存在时返回空 map
   */
  static Map<String, String> flattenPayloadFields(JsonNode event) {
    Map<String, String> result = new LinkedHashMap<>();
    JsonNode payload = event.get("payload");
    if (payload == null || !payload.isObject()) {
      return result;
    }
    var fields = payload.fields();
    while (fields.hasNext()) {
      var entry = fields.next();
      JsonNode value = entry.getValue();
      if (value.isTextual()) {
        result.put(entry.getKey(), value.asText());
      } else if (value.isNumber()) {
        result.put(entry.getKey(), String.valueOf(value.asLong()));
      } else if (value.isBoolean()) {
        result.put(entry.getKey(), String.valueOf(value.asBoolean()));
      } else if (value.isObject() || value.isArray()) {
        result.put(entry.getKey(), value.toString());
      }
    }
    return result;
  }

  /**
   * 读取 JSONL 文件的第一行事件，解析为扁平字符串映射。
   *
   * <p>委托 {@link #flattenPayloadFields} 做 payload 扁平化。
   *
   * @param filePath JSONL 文件路径
   * @return 事件字段映射；文件为空或解析失败时返回 null
   */
  private static Map<String, String> readFirstEventAsMap(Path filePath) {
    try (BufferedReader reader = Files.newBufferedReader(filePath, StandardCharsets.UTF_8)) {
      String line = reader.readLine();
      if (line == null || line.trim().isEmpty()) {
        return null;
      }
      ObjectMapper mapper = new ObjectMapper();
      JsonNode event = mapper.readTree(line.trim());
      if (!event.isObject()) {
        return null;
      }
      Map<String, String> result = flattenPayloadFields(event);
      // 顶层 type 字段
      JsonNode typeNode = event.get("type");
      if (typeNode != null && typeNode.isTextual()) {
        result.put("type", typeNode.asText());
      }
      return result;
    } catch (IOException e) {
      LOG.log(Level.FINE, "读取 rollout 文件首行失败: " + filePath, e);
      return null;
    }
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
      /* 会话唯一标识 */
      @NotBlank String sessionId,
      /* threads.db 中的线程信息，不存在时为 null */
      Map<String, String> threadInfo,
      /* session_index.jsonl 中的条目，不存在时为 null */
      Map<String, String> indexEntry,
      /* rollout 文件路径（可能不存在） */
      @NotNull Path rolloutPath,
      /* rollout 文件是否实际存在 */
      boolean hasFile) {
    /** 校验 Codex 会话发现结果参数。 */
    public CodexSessionDiscovery {
      ValidationSupport.validateCanonicalConstructor(
          CodexSessionDiscovery.class, sessionId, threadInfo, indexEntry, rolloutPath, hasFile);
    }
  }
}
