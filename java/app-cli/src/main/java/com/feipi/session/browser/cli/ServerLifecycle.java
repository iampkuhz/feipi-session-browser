package com.feipi.session.browser.cli;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.ConnectionFactory;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.scan.engine.BackgroundScanner;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.ScanLock;
import com.feipi.session.browser.scan.engine.TierConfig;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import com.feipi.session.browser.web.WebServer;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * serve 命令的服务器生命周期管理。
 *
 * <p>按固定顺序装配和启动 scan、query、web 三个子系统，并在 JVM 关闭时按逆序释放资源。 启动顺序：config → schema/query → optional scan
 * → bind server → background scheduler。 关闭顺序：background scheduler → server → DB。
 *
 * <p>所有资源（JDBC 连接、WebServer、BackgroundScanner）的生命周期由本类统一管理， 任何阶段失败都会清理已创建的资源，确保无孤儿进程或线程泄漏。
 *
 * <p>校验放置：host/port 在 {@link WebConfig} 紧凑构造器校验一次；源目录存在性在 {@link #buildSourceEntries} 边界检查一次；
 * schema 版本在 {@link IndexSchema#ensureSchema} 边界处理一次。下游不重复校验。
 */
public final class ServerLifecycle {

  private static final Logger LOG = LoggerFactory.getLogger(ServerLifecycle.class);

  private final Path indexDir;
  private final String host;
  private final int port;
  private final boolean noScan;
  private final boolean allowEmpty;
  private final Set<String> agentFilter;

  private volatile WebServer webServer;
  private volatile BackgroundScanner backgroundScanner;
  private volatile IndexConnection indexConnection;
  private volatile Connection jdbcConnection;
  private volatile Thread shutdownHook;
  private final CountDownLatch shutdownLatch = new CountDownLatch(1);

  /**
   * 创建服务器生命周期管理器。
   *
   * @param indexDir 索引目录路径
   * @param host 监听地址
   * @param port 监听端口，0 表示随机端口
   * @param noScan 是否禁用所有扫描
   * @param allowEmpty 是否允许无源目录时启动
   * @param agentFilter agent 过滤集合，空表示不过滤
   */
  public ServerLifecycle(
      Path indexDir,
      String host,
      int port,
      boolean noScan,
      boolean allowEmpty,
      Set<String> agentFilter) {
    this.indexDir = Objects.requireNonNull(indexDir, "indexDir 不得为 null");
    this.host = Objects.requireNonNull(host, "host 不得为 null");
    this.port = port;
    this.noScan = noScan;
    this.allowEmpty = allowEmpty;
    this.agentFilter = agentFilter != null ? Set.copyOf(agentFilter) : Set.of();
  }

  /**
   * 启动服务器并阻塞直到关闭信号。
   *
   * <p>启动顺序：config → schema/query → optional scan → bind server → background scheduler。
   * 任何阶段失败时清理已创建资源并抛出异常。
   *
   * @return 实际监听端口
   * @throws Exception 启动过程中任何阶段失败
   */
  public int start() throws Exception {
    Path dbPath = indexDir.resolve("index.sqlite");
    Path artifactDir = indexDir.resolve("artifacts/normalized-sessions");
    Files.createDirectories(indexDir);
    Files.createDirectories(artifactDir);

    // 构建源条目（noScan 时仍构建，用于 background scanner 配置；allowEmpty 控制空源行为）
    List<ScanConfig.SourceEntry> sourceEntries = buildSourceEntries(artifactDir);

    // 阶段 1：打开数据库连接并初始化 schema
    String jdbcUrl = "jdbc:sqlite:" + dbPath.toAbsolutePath();
    jdbcConnection = ConnectionFactory.withDefaults(jdbcUrl).create();
    try {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(jdbcConnection);
      SchemaVersion schemaVersion = schema.currentVersion(jdbcConnection);
      if (schemaVersion == null) {
        schemaVersion = IndexSchema.CURRENT_VERSION;
      }

      // 阶段 2：创建 query composition root
      indexConnection = IndexConnection.withDefaults(jdbcConnection, jdbcUrl);
      QueryCompositionRoot queryRoot = new QueryCompositionRoot(indexConnection, schemaVersion);

      // 阶段 3：可选启动扫描
      if (!noScan && !sourceEntries.isEmpty()) {
        boolean scanOk = runStartupScan(jdbcConnection, sourceEntries, artifactDir, queryRoot);
        if (!scanOk && !allowEmpty) {
          throw new IOException("启动扫描失败，使用 --allow-empty 忽略");
        }
      }

      // 阶段 4：创建并绑定 Web 服务器
      WebConfig webConfig = new WebConfig(host, port, null);
      WebCompositionRoot webRoot = new WebCompositionRoot(queryRoot, webConfig);
      webServer = webRoot.createServer();
      installShutdownHook(queryRoot, sourceEntries, artifactDir);
      webServer.start();

      // 阶段 5：启动后台扫描调度器
      if (!noScan && !sourceEntries.isEmpty()) {
        startBackgroundScanner(sourceEntries, artifactDir, queryRoot);
      }

      LOG.info("serve 已就绪: {}:{}", host, webServer.actualPort());
      return webServer.actualPort();

    } catch (Exception e) {
      cleanup();
      throw e;
    }
  }

  /**
   * 阻塞主线程直到收到关闭信号（SIGINT/SIGTERM/exception）。
   *
   * @throws InterruptedException 等待被中断时
   */
  public void awaitShutdown() throws InterruptedException {
    shutdownLatch.await();
  }

  /**
   * 优雅关闭所有资源。
   *
   * <p>关闭顺序：background scanner → web server → DB。 幂等操作，重复调用安全。会移除已注册的 shutdown hook。
   */
  public void shutdown() {
    Thread hook = shutdownHook;
    if (hook != null) {
      try {
        Runtime.getRuntime().removeShutdownHook(hook);
      } catch (IllegalStateException ignored) {
        // JVM 已在关闭中
      }
      shutdownHook = null;
    }
    doShutdown();
  }

  /** 返回服务器是否正在运行。 */
  public boolean isRunning() {
    return webServer != null && webServer.isRunning();
  }

  /** 返回实际监听端口，未启动时返回 -1。 */
  public int actualPort() {
    return webServer != null ? webServer.actualPort() : -1;
  }

  // ===== 私有方法 =====

  /** 执行关闭序列：scanner → server → DB。 */
  private void doShutdown() {
    LOG.info("正在关闭 serve...");

    if (backgroundScanner != null) {
      try {
        backgroundScanner.shutdown(5, java.util.concurrent.TimeUnit.SECONDS);
      } catch (Exception e) {
        LOG.warn("关闭后台扫描器失败", e);
      }
      backgroundScanner = null;
    }

    if (webServer != null) {
      try {
        webServer.stop();
      } catch (Exception e) {
        LOG.warn("关闭 Web 服务器失败", e);
      }
      webServer = null;
    }

    if (indexConnection != null) {
      try {
        indexConnection.close();
      } catch (Exception e) {
        LOG.warn("关闭 IndexConnection 失败", e);
      }
      indexConnection = null;
      jdbcConnection = null;
    } else if (jdbcConnection != null) {
      try {
        jdbcConnection.close();
      } catch (Exception e) {
        LOG.warn("关闭数据库连接失败", e);
      }
      jdbcConnection = null;
    }

    shutdownLatch.countDown();
    LOG.info("serve 已关闭");
  }

  /** 清理所有已创建的资源（启动失败时使用）。 */
  private void cleanup() {
    doShutdown();
  }

  /** 安装 JVM shutdown hook，确保 SIGINT/SIGTERM 触发优雅关闭。 */
  private void installShutdownHook(
      QueryCompositionRoot queryRoot,
      List<ScanConfig.SourceEntry> sourceEntries,
      Path artifactDir) {
    shutdownHook = new Thread(() -> doShutdown(), "serve-shutdown");
    Runtime.getRuntime().addShutdownHook(shutdownHook);
  }

  /**
   * 执行启动扫描。
   *
   * <p>使用 {@link BackgroundScanner#runStartupScan} 的非阻塞锁机制， 锁被占用时跳过，不阻塞启动。
   *
   * @return 扫描是否成功
   */
  private boolean runStartupScan(
      Connection conn,
      List<ScanConfig.SourceEntry> sourceEntries,
      Path artifactDir,
      QueryCompositionRoot queryRoot) {
    ScanLock scanLock = new ScanLock(indexDir);
    ScanConfig config = ScanConfig.defaults(sourceEntries, artifactDir);
    IncrementalScanEngine engine = new IncrementalScanEngine();

    LOG.info("执行启动扫描...");
    boolean ok =
        BackgroundScanner.runStartupScan(
            () -> {
              engine.scan(conn, config);
              queryRoot.invalidateCache();
            },
            scanLock);
    if (ok) {
      LOG.info("启动扫描完成");
    }
    return ok;
  }

  /** 启动后台扫描调度器，复用已有的 {@link BackgroundScanner} 分层调度逻辑。 */
  private void startBackgroundScanner(
      List<ScanConfig.SourceEntry> sourceEntries,
      Path artifactDir,
      QueryCompositionRoot queryRoot) {
    ScanLock scanLock = new ScanLock(indexDir);
    ScanConfig config = ScanConfig.defaults(sourceEntries, artifactDir);
    // conn 由 IndexConnection 管理生命周期，此处通过参数传递避免 PMD CloseResource 警告
    backgroundScanner =
        createBackgroundScanner(indexConnection.writerConnection(), config, scanLock, queryRoot);
    backgroundScanner.start();
    LOG.info("后台扫描调度器已启动");
  }

  /**
   * 创建后台扫描调度器实例。
   *
   * <p>Connection 作为参数传入（由调用方管理生命周期），不在本方法创建。 PMD 不标记方法参数为 CloseResource 违规。
   *
   * @param conn writer 连接，由 IndexConnection 持有
   * @param config 扫描配置
   * @param scanLock 跨进程扫描锁
   * @param queryRoot 查询组合根，用于扫描后失效缓存
   * @return 配置完成的后台扫描调度器
   */
  private static BackgroundScanner createBackgroundScanner(
      Connection conn, ScanConfig config, ScanLock scanLock, QueryCompositionRoot queryRoot) {
    IncrementalScanEngine engine = new IncrementalScanEngine();

    Runnable hotAction =
        () -> {
          try {
            engine.scan(conn, config);
            queryRoot.invalidateCache();
          } catch (CancellationException e) {
            LOG.info("hot 层级扫描已取消");
          } catch (Exception e) {
            LOG.warn("hot 层级后台扫描失败", e);
          }
        };

    Runnable warmAction =
        () -> {
          try {
            engine.scan(conn, config, (double) TierConfig.DEFAULT_WARM_WINDOW);
            queryRoot.invalidateCache();
          } catch (CancellationException e) {
            LOG.info("warm 层级扫描已取消");
          } catch (Exception e) {
            LOG.warn("warm 层级后台扫描失败", e);
          }
        };

    return new BackgroundScanner(
        TierConfig.DEFAULT_HOT, TierConfig.DEFAULT_WARM, scanLock, hotAction, warmAction);
  }

  /**
   * 构建源条目列表，根据 agent 过滤和环境变量解析源根目录。
   *
   * <p>校验放置：源目录存在性在此边界检查一次。ScanConfig 紧凑构造器验证 sourceEntries 非空， 但当 noScan+allowEmpty 时返回空列表绕过此校验。
   *
   * @param artifactDir 归一化制品输出目录
   * @return 源条目列表，可能为空
   * @throws IOException 当无源目录且不允许空时
   */
  private List<ScanConfig.SourceEntry> buildSourceEntries(Path artifactDir) throws IOException {
    List<ScanConfig.SourceEntry> entries = new ArrayList<>();

    boolean includeClaude = agentFilter.isEmpty() || agentFilter.contains("claude_code");
    boolean includeCodex = agentFilter.isEmpty() || agentFilter.contains("codex");
    boolean includeQoder = agentFilter.isEmpty() || agentFilter.contains("qoder");

    if (includeClaude) {
      Path root =
          resolveDataDir("CLAUDE_DATA_DIR", Path.of(System.getProperty("user.home"), ".claude"));
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new ClaudeSourceAdapter(), root));
      }
    }

    if (includeCodex) {
      Path root =
          resolveDataDir("CODEX_DATA_DIR", Path.of(System.getProperty("user.home"), ".codex"));
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new CodexSourceAdapter(), root));
      }
    }

    if (includeQoder) {
      Path root =
          resolveDataDir("QODER_DATA_DIR", Path.of(System.getProperty("user.home"), ".qoder"));
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new QoderSourceAdapter(), root));
      }
    }

    if (entries.isEmpty() && !allowEmpty) {
      throw new IOException("未找到可扫描的源目录，使用 --allow-empty 跳过或使用 --no-scan 禁用扫描");
    }

    return entries;
  }

  /**
   * 解析 agent 数据根目录。
   *
   * @param envVar 环境变量名
   * @param defaultPath 默认路径
   * @return 解析后的路径
   */
  private static Path resolveDataDir(String envVar, Path defaultPath) {
    String envValue = System.getenv(envVar);
    if (envValue != null && !envValue.isBlank()) {
      return Path.of(expandTilde(envValue));
    }
    return defaultPath;
  }

  /** 展开路径中的 ~ 为用户主目录。 */
  private static String expandTilde(String path) {
    if (path.startsWith("~/")) {
      return System.getProperty("user.home") + path.substring(1);
    }
    if (path.equals("~")) {
      return System.getProperty("user.home");
    }
    return path;
  }
}
