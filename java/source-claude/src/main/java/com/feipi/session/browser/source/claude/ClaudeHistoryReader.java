package com.feipi.session.browser.source.claude;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.source.json.JsonNodeReaders;
import com.feipi.session.browser.source.json.JsonlObjectReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.logging.Logger;

/**
 * Claude Code history.jsonl 只读解析器。
 *
 * <p>读取 {@code ~/.claude/history.jsonl}，按 sessionId 去重（保留最后一条）， 返回确定性排序的 {@link ClaudeHistoryEntry}
 * 列表。
 *
 * <p>该类是不可变的，线程安全。
 */
public final class ClaudeHistoryReader {

  private static final Logger LOG = Logger.getLogger(ClaudeHistoryReader.class.getName());

  private ClaudeHistoryReader() {
    // 工具类，禁止实例化
  }

  /**
   * 从 Claude Code 数据根目录读取并去重 history.jsonl。
   *
   * <p>文件不存在时返回空列表。解析失败的行静默跳过。
   *
   * @param rootPath Claude Code 数据根目录（通常为 {@code ~/.claude}）
   * @return 按 sessionId 排序的去重会话条目列表
   */
  public static List<ClaudeHistoryEntry> readHistory(Path rootPath) {
    if (rootPath == null || !Files.isDirectory(rootPath)) {
      return List.of();
    }

    Path historyFile = rootPath.resolve(ClaudeConstants.HISTORY_FILE);
    if (!Files.isRegularFile(historyFile)) {
      return List.of();
    }

    Map<String, ClaudeHistoryEntry> deduplicated = new LinkedHashMap<>();
    for (JsonNode node :
        JsonlObjectReader.readObjects(
            historyFile, LOG, "跳过无法解析的 history.jsonl 行", "读取 history.jsonl 失败: ")) {
      String sessionId = JsonNodeReaders.textOrEmpty(node, "sessionId");
      if (sessionId.isEmpty()) {
        continue;
      }
      String project = JsonNodeReaders.textOrEmpty(node, "project");
      String display = JsonNodeReaders.textOrEmpty(node, "display");
      long timestamp = 0;
      JsonNode tsNode = node.get("timestamp");
      if (tsNode != null && tsNode.isNumber()) {
        timestamp = tsNode.asLong();
      }
      deduplicated.put(sessionId, new ClaudeHistoryEntry(sessionId, project, display, timestamp));
    }

    List<ClaudeHistoryEntry> entries = new ArrayList<>(deduplicated.values());
    entries.sort(
        (a, b) -> {
          int cmp = Long.compare(b.timestamp(), a.timestamp());
          if (cmp != 0) {
            return cmp;
          }
          return a.sessionId().compareTo(b.sessionId());
        });
    return List.copyOf(entries);
  }
}
