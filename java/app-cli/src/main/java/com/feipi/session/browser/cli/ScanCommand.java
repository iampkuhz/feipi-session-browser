package com.feipi.session.browser.cli;

import com.feipi.session.browser.index.sqlite.ConnectionFactory;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.IncrementalScanSummary;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.ScanLock;
import com.feipi.session.browser.scan.engine.ScanLock.ScanLockUnavailableException;
import com.feipi.session.browser.scan.engine.ScanSummary;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

/**
 * scan 子命令实现。
 *
 * <p>在原 {@code scan} 命令名下切换 Java，保持参数、输出、退出码和非交互语义。 支持 {@code --full}（全量重建）、{@code
 * --incremental}（增量扫描，默认）、 {@code --agent}（源过滤）和 {@code --force}（跳过冲突提示）选项。
 *
 * <p>退出码：
 *
 * <ul>
 *   <li>0 — 扫描成功完成
 *   <li>1 — 扫描过程出错
 *   <li>2 — 扫描锁冲突或数据库被锁定
 * </ul>
 *
 * <p>校验放置：CLI 参数在 Picocli 边界解析为 typed 选项；源根目录安全检查由 {@link SourceAdapter#checkRoot} 执行； scan 锁由
 * {@link ScanLock} 在 OS 级文件锁边界执行。
 */
@Command(
    name = "scan",
    mixinStandardHelpOptions = true,
    description = "扫描本地 agent 会话数据并建立索引",
    sortOptions = false)
final class ScanCommand implements Callable<Integer> {

  /** 扫描锁超时（毫秒），默认 30 秒，可通过环境变量覆盖。 */
  private static final long DEFAULT_LOCK_TIMEOUT_MS = 30_000;

  /** 默认索引目录环境变量名。 */
  private static final String INDEX_DIR_ENV = "INDEX_DIR";

  /** 默认本地测试索引路径。 */
  private static final Path DEFAULT_INDEX_DIR =
      Path.of(
          System.getProperty("user.home"), ".local/share/feipi/session-browser/local-test-index");

  @Option(
      names = {"--incremental"},
      description = "只扫描源文件有变化的会话（默认）")
  private boolean incremental;

  @Option(
      names = {"--full"},
      description = "强制全量重建索引")
  private boolean full;

  @Option(
      names = {"--agent"},
      description = "只扫描指定 agent（claude_code, codex, qoder）",
      paramLabel = "AGENT")
  private String agent;

  @Option(
      names = {"--force", "-f"},
      description = "非交互模式：冲突时直接退出而非提示")
  private boolean force;

  @Override
  public Integer call() {
    if (full && incremental) {
      System.err.println("错误：--full 和 --incremental 不能同时使用");
      return 1;
    }

    Path indexDir = resolveIndexDir();
    Path dbPath = indexDir.resolve("index.sqlite");
    Path artifactDir = indexDir.resolve("artifacts/normalized-sessions");

    try {
      Files.createDirectories(indexDir);
      Files.createDirectories(artifactDir);
    } catch (IOException e) {
      System.err.println("错误：无法创建索引目录: " + indexDir + " (" + e.getMessage() + ")");
      return 1;
    }

    Set<String> agentFilter = resolveAgentFilter();

    ScanLock scanLock = new ScanLock(indexDir);
    long lockTimeoutMs = resolveLockTimeout();

    try (ScanLock.ScanLockHandle handle = scanLock.acquire("foreground scan", lockTimeoutMs)) {
      // 扫描锁持有期间执行扫描；handle 确保锁在完成后释放
      if (handle == null) {
        return 1;
      }
      return executeScan(dbPath, artifactDir, agentFilter);
    } catch (ScanLockUnavailableException e) {
      System.err.println("错误：扫描锁不可用");
      System.err.println("  锁文件: " + e.lockPath());
      String holder = e.holder();
      if (!holder.isEmpty()) {
        System.err.println("  持有者: " + holder);
      }
      System.err.println("  请等待当前扫描完成后重试，或使用 --force 强制终止冲突进程。");
      return 2;
    } catch (IOException e) {
      System.err.println("错误：获取扫描锁失败: " + e.getMessage());
      return 1;
    }
  }

  /** 执行扫描并返回退出码。 */
  private int executeScan(Path dbPath, Path artifactDir, Set<String> agentFilter) {
    String jdbcUrl = "jdbc:sqlite:" + dbPath.toAbsolutePath();
    List<ScanConfig.SourceEntry> sourceEntries = buildSourceEntries(agentFilter);

    if (sourceEntries.isEmpty()) {
      System.err.println("错误：未找到可扫描的源目录");
      return 1;
    }

    ScanConfig config = ScanConfig.defaults(sourceEntries, artifactDir);
    String agentLabel = agent != null ? " (" + agent + ")" : "";

    try (Connection conn = ConnectionFactory.withDefaults(jdbcUrl).create()) {
      if (incremental && !full) {
        return runIncremental(conn, config, agentLabel);
      } else {
        return runFull(conn, config, agentLabel);
      }
    } catch (SQLException e) {
      if (isDatabaseLocked(e)) {
        System.err.println("错误：数据库被锁定");
        System.err.println("  " + e.getMessage());
        System.err.println("  请等待其他进程释放锁后重试。");
        return 2;
      }
      System.err.println("错误：数据库操作失败: " + e.getMessage());
      return 1;
    }
  }

  /** 运行增量扫描。 */
  private int runIncremental(Connection conn, ScanConfig config, String agentLabel) {
    System.out.println("Starting incremental scan" + agentLabel + "...");
    long startMs = System.currentTimeMillis();

    IncrementalScanEngine engine = new IncrementalScanEngine();
    IncrementalScanSummary summary = engine.scan(conn, config);

    double elapsed = (System.currentTimeMillis() - startMs) / 1000.0;
    printIncrementalSummary(summary);
    System.out.printf("%nIncremental scan complete in %.1fs%n", elapsed);
    return summary.errorCount() == 0 ? 0 : 1;
  }

  /** 运行全量扫描。 */
  private int runFull(Connection conn, ScanConfig config, String agentLabel) {
    System.out.println("Starting full scan" + agentLabel + "...");
    long startMs = System.currentTimeMillis();

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(conn, config);

    double elapsed = (System.currentTimeMillis() - startMs) / 1000.0;
    printFullSummary(summary);
    System.out.printf("%nScan complete in %.1fs%n", elapsed);
    return summary.errorCount() == 0 ? 0 : 1;
  }

  /** 构建源条目列表，根据 agent 过滤和环境变量解析源根目录。 */
  private List<ScanConfig.SourceEntry> buildSourceEntries(Set<String> agentFilter) {
    List<ScanConfig.SourceEntry> entries = new ArrayList<>();

    boolean includeClaude = agentFilter.isEmpty() || agentFilter.contains("claude_code");
    boolean includeCodex = agentFilter.isEmpty() || agentFilter.contains("codex");
    boolean includeQoder = agentFilter.isEmpty() || agentFilter.contains("qoder");

    if (includeClaude) {
      Path root = resolveClaudeRoot();
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new ClaudeSourceAdapter(), root));
      }
    }

    if (includeCodex) {
      Path root = resolveCodexRoot();
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new CodexSourceAdapter(), root));
      }
    }

    if (includeQoder) {
      Path root = resolveQoderRoot();
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new QoderSourceAdapter(), root));
      }
    }

    return entries;
  }

  /** 解析 agent 过滤器。 */
  private Set<String> resolveAgentFilter() {
    if (agent == null || agent.isBlank()) {
      return Set.of();
    }
    return Set.of(agent.toLowerCase());
  }

  /** 解析索引目录。 */
  private static Path resolveIndexDir() {
    String envValue = System.getenv(INDEX_DIR_ENV);
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return DEFAULT_INDEX_DIR;
  }

  /** 解析 Claude 数据根目录。 */
  private static Path resolveClaudeRoot() {
    String envValue = System.getenv("CLAUDE_DATA_DIR");
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return Path.of(System.getProperty("user.home"), ".claude");
  }

  /** 解析 Codex 数据根目录。 */
  private static Path resolveCodexRoot() {
    String envValue = System.getenv("CODEX_DATA_DIR");
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return Path.of(System.getProperty("user.home"), ".codex");
  }

  /** 解析 Qoder 数据根目录。 */
  private static Path resolveQoderRoot() {
    String envValue = System.getenv("QODER_DATA_DIR");
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(PathUtils.expandTilde(envValue));
    }
    return Path.of(System.getProperty("user.home"), ".qoder");
  }

  /** 解析扫描锁超时（毫秒）。 */
  private static long resolveLockTimeout() {
    String envValue = System.getenv("SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS");
    if (envValue != null && !envValue.isBlank()) {
      try {
        double seconds = Double.parseDouble(envValue);
        if (seconds >= 0) {
          return (long) (seconds * 1000);
        }
      } catch (NumberFormatException ignored) {
        // 使用默认值
      }
    }
    return DEFAULT_LOCK_TIMEOUT_MS;
  }

  /** 判断 SQLException 是否为数据库锁定错误。 */
  private static boolean isDatabaseLocked(SQLException e) {
    String msg = e.getMessage();
    return msg != null && msg.toLowerCase().contains("database is locked");
  }

  /** 打印全量扫描汇总。 */
  private static void printFullSummary(ScanSummary summary) {
    int claudeCount = getCountForSource(summary, "claude_code");
    int codexCount = getCountForSource(summary, "codex");
    int qoderCount = getCountForSource(summary, "qoder");
    int total = summary.successCount();

    System.out.printf("  Claude Code: %d sessions%n", claudeCount);
    System.out.printf("  Codex:       %d sessions%n", codexCount);
    if (qoderCount > 0) {
      System.out.printf("  Qoder:       %d sessions%n", qoderCount);
    }
    System.out.printf("  Total:       %d sessions%n", total);
  }

  /** 打印增量扫描汇总。 */
  private static void printIncrementalSummary(IncrementalScanSummary summary) {
    int claudeCount = getCountForSource(summary, "claude_code");
    int codexCount = getCountForSource(summary, "codex");
    int qoderCount = getCountForSource(summary, "qoder");
    int skipped = summary.unchangedCount() + summary.skippedCount();
    int total = summary.successCount();

    System.out.printf("  Updated Claude: %d sessions%n", claudeCount);
    System.out.printf("  Updated Codex:  %d sessions%n", codexCount);
    if (qoderCount > 0) {
      System.out.printf("  Updated Qoder:  %d sessions%n", qoderCount);
    }
    System.out.printf("  Skipped:        %d sessions%n", skipped);
    System.out.printf("  Total updated:  %d sessions%n", total);
  }

  /** 从 ScanSummary 提取指定源的计数。 */
  private static int getCountForSource(ScanSummary summary, String sourceIdValue) {
    return summary.perSourceCount().entrySet().stream()
        .filter(e -> e.getKey().getValue().equals(sourceIdValue))
        .mapToInt(Map.Entry::getValue)
        .sum();
  }

  /** 从 IncrementalScanSummary 提取指定源的成功计数。 */
  private static int getCountForSource(IncrementalScanSummary summary, String sourceIdValue) {
    return summary.perSourceCount().entrySet().stream()
        .filter(e -> e.getKey().getValue().equals(sourceIdValue))
        .mapToInt(Map.Entry::getValue)
        .sum();
  }
}
