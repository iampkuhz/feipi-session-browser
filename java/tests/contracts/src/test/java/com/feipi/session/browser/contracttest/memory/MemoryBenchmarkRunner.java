package com.feipi.session.browser.contracttest.memory;

import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.ScanProgress;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.List;

/**
 * 独立 JVM 内存基准测试运行器。
 *
 * <p>生成合成 rollout 数据并执行完整扫描管线（scan-engine → SQLite → artifact）。 用于验证不同堆预算下的内存行为。
 *
 * <p>用法：{@code java MemoryBenchmarkRunner <dataDir> <sessions> <eventsPerSession>}
 */
public class MemoryBenchmarkRunner {

  public static void main(String[] args) throws Exception {
    if (args.length != 3) {
      System.err.println("用法: MemoryBenchmarkRunner <dataDir> <sessions> <eventsPerSession>");
      System.exit(1);
    }

    Path dataDir = Path.of(args[0]);
    int sessions = Integer.parseInt(args[1]);
    int eventsPerSession = Integer.parseInt(args[2]);

    System.out.printf("=== 内存基准测试 ===%n");
    System.out.printf("数据目录: %s%n", dataDir);
    System.out.printf("会话数: %d, 每会话事件数: %d%n", sessions, eventsPerSession);
    System.out.printf("JVM 堆: -Xmx%s%n", System.getProperty("xmx", "unknown"));

    // 生成合成数据
    Path codexRoot = dataDir.resolve(".codex");
    generateSyntheticData(codexRoot, sessions, eventsPerSession);

    // 执行扫描
    Path indexDir = dataDir.resolve("index");
    Files.createDirectories(indexDir);
    Path dbPath = indexDir.resolve("sessions.db");
    Path artifactDir = indexDir.resolve("artifacts/normalized-sessions");

    String jdbcUrl = "jdbc:sqlite:" + dbPath.toAbsolutePath();
    try (Connection conn = DriverManager.getConnection(jdbcUrl)) {
      SqliteIndexWriter writer = new SqliteIndexWriter(conn);
      IncrementalScanEngine engine = new IncrementalScanEngine();

      SourceAdapter adapter = new CodexSourceAdapter();
      ScanConfig config =
          ScanConfig.defaults(List.of(new ScanConfig.SourceEntry(adapter, codexRoot)), artifactDir);

      // 首次重建
      System.out.println("执行首次重建扫描...");
      long memBefore = sampleMemoryMb();
      var summary1 = engine.scan(writer, config, null, null, new SilentProgress());
      long memAfter = sampleMemoryMb();
      System.out.printf(
          "首次重建完成: 候选=%d, 新增=%d, 错误=%d, 内存峰值=%dMB%n",
          summary1.totalCandidates(),
          summary1.newCount(),
          summary1.errorCount(),
          memAfter - memBefore);

      if (summary1.errorCount() > 0) {
        System.err.println("首次扫描失败: errors=" + summary1.errorCount());
        System.exit(1);
      }

      // 验证发现数和入库数
      if (summary1.totalCandidates() == 0) {
        System.err.println("发现 0 个候选，测试数据生成失败");
        System.exit(1);
      }
      System.out.printf(
          "BENCHMARK_RESULT: candidates=%d, new=%d%n",
          summary1.totalCandidates(), summary1.newCount());

      // 查询 SQLite 行数
      long sessionCount = countSessions(conn);
      long artifactCount = countArtifacts(conn);
      System.out.printf(
          "BENCHMARK_RESULT: sqlite_sessions=%d, sqlite_artifacts=%d%n",
          sessionCount, artifactCount);

      // 多轮 unchanged
      for (int round = 1; round <= 3; round++) {
        System.out.printf("执行第 %d 轮 unchanged 扫描...%n", round);
        long memBeforeN = sampleMemoryMb();
        var summaryN = engine.scan(writer, config, null, null, new SilentProgress());
        long memAfterN = sampleMemoryMb();
        System.out.printf(
            "第 %d 轮完成: 候选=%d, 未变=%d, 错误=%d, 内存=%dMB%n",
            round,
            summaryN.totalCandidates(),
            summaryN.unchangedCount(),
            summaryN.errorCount(),
            memAfterN - memBeforeN);

        if (summaryN.errorCount() > 0) {
          System.err.println("第 " + round + " 轮扫描失败: errors=" + summaryN.errorCount());
          System.exit(1);
        }
        System.out.printf(
            "BENCHMARK_RESULT: round=%d, candidates=%d, unchanged=%d%n",
            round, summaryN.totalCandidates(), summaryN.unchangedCount());
      }

      System.out.println("=== 测试通过 ===");
    }
  }

  private static void generateSyntheticData(Path root, int sessions, int eventsPerSession)
      throws IOException {
    Path sessionsDir = root.resolve("sessions/2025/01/01");
    Files.createDirectories(sessionsDir);

    // 生成 session_index.jsonl，每个会话一条记录
    Path sessionIndex = root.resolve("session_index.jsonl");
    try (BufferedWriter indexWriter =
        Files.newBufferedWriter(sessionIndex, StandardCharsets.UTF_8)) {
      for (int i = 0; i < sessions; i++) {
        String sessionId = "session-" + i;
        // 写入 session_index.jsonl 条目
        indexWriter.write(
            String.format(
                "{\"id\":\"%s\",\"thread_name\":\"Test Thread %d\",\"updated_at\":\"2025-01-01\"}\n",
                sessionId, i));
      }
    }

    // 生成多个会话的 rollout 文件
    for (int i = 0; i < sessions; i++) {
      String sessionId = "session-" + i;
      Path rollout = sessionsDir.resolve(String.format("rollout-20250101-%s.jsonl", sessionId));
      generateRollout(rollout, i, eventsPerSession);
    }
  }

  private static void generateRollout(Path file, int sessionId, int eventCount) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
      // 写入会话元数据事件
      writer.write(
          String.format(
              "{\"type\":\"session_meta\",\"payload\":{\"id\":\"session-%d\","
                  + "\"cwd\":\"/test/project-%d\",\"model\":\"gpt-4\",\"source\":\"{\\\"git\\\":{\\\"branch\\\":\\\"main\\\"}}\"}}",
              sessionId, sessionId));
      writer.newLine();

      // 生成事件：交替 user/assistant/tool 消息，每个事件有实质 payload
      for (int i = 1; i < eventCount; i++) {
        String event;
        switch (i % 4) {
          case 0 ->
              event =
                  String.format(
                      "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\","
                          + "\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"question %d from session %d with padding text to simulate realistic payload size\"}]}}",
                      i, sessionId);
          case 1 ->
              event =
                  String.format(
                      "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\","
                          + "\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"answer %d from session %d with substantial padding text to increase memory footprint and simulate real conversation context\"}]}}",
                      i, sessionId);
          case 2 ->
              event =
                  String.format(
                      "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\","
                          + "\"call_id\":\"call-%d-%d\",\"name\":\"shell\",\"content\":\"execute command %d\"}}",
                      sessionId, i, i);
          default ->
              event =
                  String.format(
                      "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\","
                          + "\"call_id\":\"call-%d-%d\",\"output\":\"result %d with output padding to simulate realistic tool response size\"}}",
                      sessionId, i - 1, i);
        }
        writer.write(event);
        writer.newLine();
      }
    }
  }

  /** 静默进度回调，不输出日志。 */
  private static final class SilentProgress implements ScanProgress {
    @Override
    public void onPhaseStart(String phaseName) {}

    @Override
    public void onPhaseEnd(String phaseName, long durationMs) {}

    @Override
    public void onSourceStart(String sourceName, int candidateCount) {}

    @Override
    public void onCandidateProcessed(String sourceName, int processed, int total) {}

    @Override
    public void onSourceEnd(String sourceName, int successCount) {}
  }

  /** 采样当前堆内存使用（MB）。 */
  private static long sampleMemoryMb() {
    Runtime runtime = Runtime.getRuntime();
    long used = runtime.totalMemory() - runtime.freeMemory();
    return used / (1024 * 1024);
  }

  /** 查询 sessions 表行数。 */
  private static long countSessions(Connection conn) throws Exception {
    try (var stmt = conn.createStatement();
        var rs = stmt.executeQuery("SELECT COUNT(*) FROM sessions")) {
      return rs.next() ? rs.getLong(1) : 0;
    }
  }

  /** 查询 session_artifacts 表行数。 */
  private static long countArtifacts(Connection conn) throws Exception {
    try (var stmt = conn.createStatement();
        var rs = stmt.executeQuery("SELECT COUNT(*) FROM session_artifacts")) {
      return rs.next() ? rs.getLong(1) : 0;
    }
  }
}
