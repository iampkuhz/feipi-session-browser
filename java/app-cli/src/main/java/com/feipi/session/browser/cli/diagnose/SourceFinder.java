package com.feipi.session.browser.cli.diagnose;

import com.feipi.session.browser.source.claude.ClaudeDiscovery;
import com.feipi.session.browser.source.claude.ClaudeDiscovery.ClaudeSessionDiscovery;
import com.feipi.session.browser.source.claude.ClaudeHistoryEntry;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * 根据 agent + sessionId 定位会话文件。
 *
 * <p>当前仅支持 Claude Code 源。其他 agent 类型返回 UNAVAILABLE。
 */
final class SourceFinder {

  private static final Logger LOG = Logger.getLogger(SourceFinder.class.getName());

  private SourceFinder() {}

  /**
   * Claude Code 源定位结果。
   *
   * @param transcriptPath transcript 文件路径
   * @param transcriptExists transcript 文件是否存在
   * @param transcriptSizeBytes transcript 文件大小（字节）
   * @param subagentsDir subagent 目录路径
   * @param subagentsDirExists subagent 目录是否存在
   * @param subagentJsonlFiles subagent JSONL 文件列表
   * @param metaFromHistory 从 history 提取的元数据
   */
  record ClaudeSessionLocation(
      Path transcriptPath,
      boolean transcriptExists,
      long transcriptSizeBytes,
      Path subagentsDir,
      boolean subagentsDirExists,
      List<Path> subagentJsonlFiles,
      Map<String, String> metaFromHistory) {}

  /**
   * 在 Claude Code 数据目录中定位指定 sessionId 的会话。
   *
   * @param sourceRoot Claude 数据根目录（通常 ~/.claude）
   * @param sessionId 目标 session UUID
   * @return 定位结果，session 不存在时 empty
   */
  static Optional<ClaudeSessionLocation> findClaudeSession(Path sourceRoot, String sessionId) {
    if (sourceRoot == null || !Files.isDirectory(sourceRoot)) {
      return Optional.empty();
    }

    List<ClaudeSessionDiscovery> discoveries =
        ClaudeDiscovery.discoverSessionsWithHistory(sourceRoot);

    for (ClaudeSessionDiscovery disc : discoveries) {
      ClaudeHistoryEntry entry = disc.entry();
      if (!sessionId.equals(entry.sessionId())) {
        continue;
      }

      Path transcriptPath = disc.transcriptPath();
      boolean transcriptExists = disc.hasFile();
      long sizeBytes = 0;
      if (transcriptExists) {
        try {
          sizeBytes = Files.size(transcriptPath);
        } catch (IOException e) {
          LOG.log(Level.FINE, "无法读取 transcript 大小: " + transcriptPath, e);
        }
      }

      // 子会话 subagent 目录
      Path subagentsDir = resolveSubagentsDir(transcriptPath);
      boolean subagentsDirExists = Files.isDirectory(subagentsDir);
      List<Path> subagentFiles = List.of();
      if (subagentsDirExists) {
        subagentFiles = listSubagentJsonl(subagentsDir);
      }

      // 从 history entry 提取元数据
      Map<String, String> meta = new LinkedHashMap<>();
      if (entry.display() != null && !entry.display().isBlank()) {
        meta.put("display", entry.display());
      }
      meta.put("project", entry.project());
      meta.put("timestamp", String.valueOf(entry.timestamp()));

      return Optional.of(
          new ClaudeSessionLocation(
              transcriptPath,
              transcriptExists,
              sizeBytes,
              subagentsDir,
              subagentsDirExists,
              subagentFiles,
              Map.copyOf(meta)));
    }

    return Optional.empty();
  }

  private static Path resolveSubagentsDir(Path transcriptPath) {
    String fileName = transcriptPath.getFileName().toString();
    String stem =
        fileName.endsWith(".jsonl") ? fileName.substring(0, fileName.length() - 6) : fileName;
    return transcriptPath.resolveSibling(stem).resolve("subagents");
  }

  private static List<Path> listSubagentJsonl(Path subagentsDir) {
    List<Path> files = new ArrayList<>();
    try (var stream = Files.list(subagentsDir)) {
      stream
          .filter(Files::isRegularFile)
          .filter(p -> p.getFileName().toString().endsWith(".jsonl"))
          .sorted()
          .forEach(files::add);
    } catch (IOException e) {
      LOG.log(Level.FINE, "读取 subagent 目录失败: " + subagentsDir, e);
    }
    return List.copyOf(files);
  }
}
