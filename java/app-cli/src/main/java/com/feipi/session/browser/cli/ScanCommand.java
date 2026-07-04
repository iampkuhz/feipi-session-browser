package com.feipi.session.browser.cli;

import com.feipi.session.browser.index.sqlite.ConnectionFactory;
import com.feipi.session.browser.index.sqlite.DatabaseUpgrader;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.IncrementalScanSummary;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.ScanLock;
import com.feipi.session.browser.scan.engine.ScanLock.ScanLockUnavailableException;
import com.feipi.session.browser.scan.engine.ScanProgress;
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

  @Option(
      names = {"--index-dir"},
      description = "索引目录（默认遵循 XDG 规范）")
  private String indexDirOption;

  @Override
  public Integer call() {
    if (full && incremental) {
      System.err.println("错误：--full 和 --incremental 不能同时使用");
      return 1;
    }

    Path indexDir = PathResolver.resolveDataDir(indexDirOption, INDEX_DIR_ENV);
    RuntimePaths paths = RuntimePaths.fromDataDir(indexDir);

    try {
      paths.ensureDirectories();
    } catch (IOException e) {
      System.err.println("错误：无法创建或写入运行时目录: " + e.getMessage());
      return 1;
    }

    Path dbPath = paths.dbPath();
    Path artifactDir = paths.artifactDir();

    Set<String> agentFilter;
    try {
      agentFilter = resolveAgentFilter();
    } catch (IllegalArgumentException e) {
      System.err.println("错误：agent 参数无效：" + e.getMessage());
      return 1;
    }

    return acquireLockAndExecuteScan(indexDir, dbPath, artifactDir, agentFilter);
  }

  /** 获取扫描锁并执行扫描。 */
  private int acquireLockAndExecuteScan(
      Path indexDir, Path dbPath, Path artifactDir, Set<String> agentFilter) {
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

    // 升级前备份 + schema migration + 版本兼容性检查
    String appVersion = BuildInfoVersionProvider.readAppVersion();
    Path backupDir = dbPath.getParent().resolve("backups");
    DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults(appVersion, backupDir);
    try {
      upgrader.upgrade(dbPath);
    } catch (DatabaseUpgrader.UpgradeException e) {
      System.err.println("错误：数据库升级失败: " + e.getMessage());
      return 1;
    }

    if (sourceEntries.isEmpty()) {
      System.out.println("未找到可扫描的源目录，已创建空索引。");
      System.out.println("可配置 CLAUDE_DATA_DIR / CODEX_DATA_DIR / QODER_DATA_DIR 后重新运行 scan。");
      System.out.println("  Claude Code: 0 sessions");
      System.out.println("  Codex:       0 sessions");
      System.out.println("  Total:       0 sessions");
      return 0;
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
    ScanProgress progress = new ConsoleScanProgress();
    IncrementalScanSummary summary = engine.scan(conn, config, null, null, progress);

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
    ScanProgress progress = new ConsoleScanProgress();
    ScanSummary summary = engine.scan(conn, config, progress);

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
    String normalized = agent.toLowerCase();
    if (!Set.of("claude_code", "codex", "qoder").contains(normalized)) {
      throw new IllegalArgumentException("未知 agent: " + agent + "（支持 claude_code, codex, qoder）");
    }
    return Set.of(normalized);
  }

  /** 解析 Claude 数据根目录。 */
  private static Path resolveClaudeRoot() {
    return PathResolver.resolveSourceDataDir(
        "CLAUDE_DATA_DIR", Path.of(System.getProperty("user.home"), ".claude"));
  }

  /** 解析 Codex 数据根目录。 */
  private static Path resolveCodexRoot() {
    return PathResolver.resolveSourceDataDir(
        "CODEX_DATA_DIR", Path.of(System.getProperty("user.home"), ".codex"));
  }

  /** 解析 Qoder 数据根目录。 */
  private static Path resolveQoderRoot() {
    return PathResolver.resolveSourceDataDir(
        "QODER_DATA_DIR", Path.of(System.getProperty("user.home"), ".qoder"));
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
    int total = sumAllSourceCounts(summary);

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
    int total = sumAllSourceCounts(summary);

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

  /** 对 ScanSummary 所有源的计数求和，确保 Total 与分项一致。 */
  private static int sumAllSourceCounts(ScanSummary summary) {
    return summary.perSourceCount().values().stream().mapToInt(Integer::intValue).sum();
  }

  /** 对 IncrementalScanSummary 所有源的计数求和，确保 Total 与分项一致。 */
  private static int sumAllSourceCounts(IncrementalScanSummary summary) {
    return summary.perSourceCount().values().stream().mapToInt(Integer::intValue).sum();
  }

  /**
   * 控制台扫描进度实现。
   *
   * <p>将扫描进度以人类可读的方式输出到 stdout：
   *
   * <ul>
   *   <li>{@code onSourceStart} — 打印 {@code Scanning <sourceName>... (N sessions)}
   *   <li>{@code onCandidateProcessed} — 每处理 50 个或每 5%（取较小间隔）使用 {@code \r} 覆盖当前行打印进度条
   *   <li>{@code onSourceEnd} — 打印完成状态并换行
   * </ul>
   */
  private static final class ConsoleScanProgress implements ScanProgress {

    private static final int BAR_WIDTH = 30;

    private static final String[] SOURCE_DISPLAY_NAMES = {
      "claude_code", "Claude Code",
      "codex", "Codex",
      "qoder", "Qoder"
    };

    /** 当前源上次打印进度时的已处理数量，用于控制打印频率。 */
    private int lastPrintedProcessed = -1;

    /** 打印频率间隔：每处理多少个候选项更新一次。 */
    private int printInterval;

    @Override
    public void onSourceStart(String sourceName, int candidateCount) {
      lastPrintedProcessed = -1;

      // 计算打印间隔：50 个或 5%，取较小值，至少为 1
      int fivePercent = Math.max(1, candidateCount / 20);
      printInterval = Math.min(50, fivePercent);
      if (printInterval < 1) {
        printInterval = 1;
      }

      String displayName = toDisplayName(sourceName);
      System.out.printf("Scanning %s... (%d sessions)%n", displayName, candidateCount);
    }

    @Override
    public void onCandidateProcessed(String sourceName, int processed, int total) {
      if (total <= 0) {
        return;
      }
      // 达到打印间隔或处理完毕时更新进度
      boolean atInterval = (processed - lastPrintedProcessed) >= printInterval;
      boolean atEnd = (processed == total);
      if (!atInterval && !atEnd) {
        return;
      }
      lastPrintedProcessed = processed;

      int percent = (int) ((processed * 100L) / total);
      int filled = (int) ((processed * (long) BAR_WIDTH) / total);
      if (filled > BAR_WIDTH) {
        filled = BAR_WIDTH;
      }

      StringBuilder bar = new StringBuilder(BAR_WIDTH + 4);
      bar.append('[');
      for (int i = 0; i < BAR_WIDTH; i++) {
        if (i < filled) {
          bar.append('=');
        } else if (i == filled) {
          bar.append('>');
        } else {
          bar.append(' ');
        }
      }
      bar.append(']');

      System.out.printf("\r  %s %d/%d (%d%%)", bar, processed, total, percent);
      if (atEnd) {
        System.out.println();
      }
      System.out.flush();
    }

    @Override
    public void onSourceEnd(String sourceName, int successCount) {
      String displayName = toDisplayName(sourceName);
      // 如果 onCandidateProcessed 没有因为 total=0 而打印过，仍需确保换行
      System.out.printf("  %s: %d sessions indexed%n", displayName, successCount);
    }

    /** 将 source id 值转换为人类可读名称。 */
    private static String toDisplayName(String sourceName) {
      for (int i = 0; i < SOURCE_DISPLAY_NAMES.length; i += 2) {
        if (SOURCE_DISPLAY_NAMES[i].equals(sourceName)) {
          return SOURCE_DISPLAY_NAMES[i + 1];
        }
      }
      return sourceName;
    }
  }
}
