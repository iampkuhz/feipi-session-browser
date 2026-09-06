package com.feipi.session.browser.cli;

import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.ConnectionFactory;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.DatabaseUpgrader;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.scan.engine.BackgroundScanner;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.ScanCancelToken;
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
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * serve 命令的服务器生命周期管理。
 *
 * <p>按固定顺序装配和启动 scan、query、web 三个子系统，并在 JVM 关闭时按逆序释放资源。 启动顺序：config → schema/query → bind server →
 * ready → background scheduler。 关闭顺序：background scheduler → server → DB。
 *
 * <p>所有资源（JDBC 连接、WebServer、BackgroundScanner）的生命周期由本类统一管理， 任何阶段失败都会清理已创建的资源，确保无孤儿进程或线程泄漏。
 *
 * <p>校验放置：host/port 在 {@link WebConfig} 紧凑构造器校验一次；源目录存在性在 {@link #buildSourceEntries} 边界检查一次；
 * schema 版本在 {@link IndexSchema#ensureSchema} 边界处理一次。下游不重复校验。
 */
public final class ServerLifecycle {

  private static final Logger LOG = LoggerFactory.getLogger(ServerLifecycle.class);

  /** Web 服务器就绪探测的最大等待时间（毫秒）。 */
  private static final long READINESS_TIMEOUT_MS = 10_000L;

  /** Web 服务器就绪探测间隔（毫秒）。 */
  private static final long READINESS_POLL_MS = 100L;

  /** 单次 health endpoint 探测超时（毫秒）。 */
  private static final int READINESS_HTTP_TIMEOUT_MS = 1_000;

  private final Path indexDir;
  private final String host;
  private final int port;
  private final boolean noScan;
  private final boolean allowEmpty;
  private final Set<String> agentFilter;

  private volatile WebServer webServer;
  private volatile WebCompositionRoot webRoot;
  private volatile BackgroundScanner backgroundScanner;
  private volatile IndexConnection indexConnection;
  private volatile Connection jdbcConnection;
  private volatile Thread shutdownHook;
  private final CountDownLatch shutdownLatch = new CountDownLatch(1);
  private volatile List<ScanConfig.SourceEntry> sourceEntries;
  private volatile Path artifactDir;

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
   * <p>启动顺序：config → schema/query → bind server；ready 后显式激活 background scheduler。
   * 任何阶段失败时清理已创建资源并抛出异常。
   *
   * @return 实际监听端口
   * @throws Exception 启动过程中任何阶段失败
   */
  public int start() throws Exception {
    long startNanos = System.nanoTime();
    Path dbPath = indexDir.resolve(RuntimePaths.DB_FILE_NAME);
    Path artifactDir = indexDir.resolve("artifacts/normalized-sessions");
    Files.createDirectories(indexDir);
    Files.createDirectories(artifactDir);
    LOG.info("运行时目录就绪");

    // 阶段 0：升级前备份 + schema migration + 版本兼容性检查
    String appVersion = BuildInfoVersionProvider.readAppVersion();
    Path backupDir = indexDir.resolve("backups");
    DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults(appVersion, backupDir);
    try {
      upgrader.upgrade(dbPath);
    } catch (DatabaseUpgrader.UpgradeException e) {
      LOG.error("数据库升级失败", e);
      throw new IOException("数据库升级失败: " + e.getMessage(), e);
    }

    // 构建源条目（noScan 时仍构建，用于 background scanner 配置；allowEmpty 控制空源行为）
    List<ScanConfig.SourceEntry> sourceEntries = buildSourceEntries(artifactDir);
    LOG.info("发现 {} 个源", sourceEntries.size());

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
      LOG.info("数据库 schema 就绪 (v{})", schemaVersion.version());

      // 阶段 2：创建 query composition root
      indexConnection = IndexConnection.withDefaults(jdbcConnection, jdbcUrl);
      QueryCompositionRoot queryRoot = createQueryCompositionRoot(indexConnection, schemaVersion);
      LOG.info("查询引擎就绪");

      // 阶段 3：创建并绑定 Web 服务器（先于扫描，确保尽快可访问）
      WebConfig webConfig = new WebConfig(host, port, "/static");
      webRoot = new WebCompositionRoot(queryRoot, webConfig);
      webServer = webRoot.createServer();
      this.sourceEntries = sourceEntries;
      this.artifactDir = artifactDir;
      installShutdownHook(queryRoot, sourceEntries, artifactDir);
      LOG.info("启动 Web 服务器");
      webServer.start();
      int actualPort = webServer.actualPort();
      waitForHealth(actualPort);

      // 写入 PID 文件供 stop 命令使用
      writePidFile(actualPort);

      long elapsedMs = (System.nanoTime() - startNanos) / 1_000_000;
      LOG.info("serve 启动完成: 耗时 {}ms", elapsedMs);

      return actualPort;

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

  /**
   * 激活后台扫描调度器。
   *
   * <p>应在 ServeCommand 打印 "ready" 后调用，确保 ready 输出先于任何 bootstrap 开始。 如果 noScan 或无可用源，则跳过扫描。
   */
  public synchronized void activateBackgroundScanner() {
    if (!isRunning() || backgroundScanner != null) {
      return;
    }
    if (noScan) {
      LOG.info("跳过扫描: --no-scan");
      return;
    }
    List<ScanConfig.SourceEntry> entries = this.sourceEntries;
    Path dir = this.artifactDir;
    if (entries == null || entries.isEmpty()) {
      LOG.info("跳过扫描: 无可用源");
      return;
    }
    startBackgroundScanner(entries, dir);
  }

  // ===== 私有方法 =====

  /** 使用具体 SQLite 适配器装配 application 查询用例。 */
  private static QueryCompositionRoot createQueryCompositionRoot(
      IndexConnection indexConnection, SchemaVersion schemaVersion) {
    SqliteSessionQueryRepository sessionRepository =
        new SqliteSessionQueryRepository(indexConnection);
    SqliteAggregateQueryRepository aggregateRepository =
        new SqliteAggregateQueryRepository(indexConnection);
    SqliteSessionDetailRepository detailRepository =
        new SqliteSessionDetailRepository(sessionRepository);
    return new QueryCompositionRoot(
        sessionRepository,
        aggregateRepository,
        detailRepository,
        NormalizedArtifactLoader::load,
        schemaVersion.version(),
        QueryCache.withDefaultSize());
  }

  /** 执行关闭序列：scanner → server → DB → 清理 PID 文件。 */
  private synchronized void doShutdown() {
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

    // 正常关闭时清理 PID 文件
    PidFile.delete(indexDir);

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
   * 写入 PID 文件供 stop 命令定位和验证进程。
   *
   * <p>写入失败仅记录警告，不阻止 serve 运行。PID 文件包含 PID、端口、主机、索引目录和启动时间。
   *
   * @param actualPort 实际监听端口
   */
  private void writePidFile(int actualPort) {
    try {
      PidFile.write(indexDir, ProcessHandle.current().pid(), actualPort, host);
    } catch (IOException e) {
      LOG.warn("写入 PID 文件失败，stop 命令将无法自动识别此进程: {}", e.getMessage());
    }
  }

  /** 启动后台扫描调度器，含引导扫描和 hot/warm 周期调度。 */
  private void startBackgroundScanner(
      List<ScanConfig.SourceEntry> sourceEntries, Path artifactDir) {
    ScanLock scanLock = new ScanLock(indexDir);
    ScanConfig config = ScanConfig.defaults(sourceEntries, artifactDir);
    // conn 由 IndexConnection 管理生命周期，此处通过参数传递避免 PMD CloseResource 警告
    backgroundScanner =
        createBackgroundScanner(indexConnection.writerConnection(), config, scanLock);
    backgroundScanner.start();
  }

  /**
   * 创建后台扫描调度器实例，含引导动作。
   *
   * <p>Connection 作为参数传入（由调用方管理生命周期），不在本方法创建。
   *
   * @param conn writer 连接，由 IndexConnection 持有
   * @param config 扫描配置
   * @param scanLock 跨进程扫描锁
   * @return 配置完成的后台扫描调度器
   */
  private BackgroundScanner createBackgroundScanner(
      Connection conn, ScanConfig config, ScanLock scanLock) {
    IncrementalScanEngine engine = new IncrementalScanEngine();

    Consumer<ScanCancelToken> bootstrapAction = createScanAction(engine, conn, config, null);
    Consumer<ScanCancelToken> hotAction = createScanAction(engine, conn, config, null);
    Consumer<ScanCancelToken> warmAction =
        createScanAction(engine, conn, config, (double) TierConfig.DEFAULT_WARM_WINDOW);

    return new BackgroundScanner(
        TierConfig.DEFAULT_HOT,
        TierConfig.DEFAULT_WARM,
        scanLock,
        hotAction,
        warmAction,
        bootstrapAction,
        java.time.Clock.systemUTC());
  }

  /** 将引擎的取消和失败结果传回调度器，已写入的部分结果同样需要清除查询缓存。 */
  private Consumer<ScanCancelToken> createScanAction(
      IncrementalScanEngine engine, Connection conn, ScanConfig config, Double maxAgeSeconds) {
    return token -> {
      token.throwIfCancelled();
      try {
        var summary = engine.scan(new SqliteIndexWriter(conn), config, maxAgeSeconds, token);
        token.throwIfCancelled();
        if (summary.errorCount() > 0 || !summary.issues().isEmpty()) {
          throw new IllegalStateException("后台扫描返回失败结果: errors=" + summary.errorCount());
        }
      } finally {
        webRoot.invalidateCache();
      }
    };
  }

  /**
   * 等待 health endpoint 真正可用。
   *
   * <p>Javalin start 返回后端口可能已绑定但 handler 尚未完成首个请求准备；在高并发构建机上这会导致 CLI smoke 立刻访问时偶发 read
   * timeout。这里用短轮询把 {@link #start()} 的语义收敛为“返回时服务可响应健康检查”。
   *
   * @param actualPort 实际监听端口
   * @throws IOException health endpoint 在超时前不可用
   */
  private void waitForHealth(int actualPort) throws IOException {
    long deadline = System.currentTimeMillis() + READINESS_TIMEOUT_MS;
    IOException lastFailure = null;
    while (System.currentTimeMillis() < deadline) {
      try {
        if (probeHealth(actualPort)) {
          return;
        }
      } catch (IOException e) {
        lastFailure = e;
      }
      try {
        Thread.sleep(READINESS_POLL_MS);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IOException("等待 health endpoint 就绪时被中断", e);
      }
    }
    IOException failure = new IOException("health endpoint 未在超时前就绪: " + host + ":" + actualPort);
    if (lastFailure != null) {
      failure.addSuppressed(lastFailure);
    }
    throw failure;
  }

  /**
   * 发起单次 health endpoint 探测。
   *
   * @param actualPort 实际监听端口
   * @return 响应码为 200 时返回 true
   * @throws IOException 网络连接或读取失败
   */
  private boolean probeHealth(int actualPort) throws IOException {
    String probeHost = "0.0.0.0".equals(host) || "::".equals(host) ? "127.0.0.1" : host;
    URI uri = URI.create("http://" + probeHost + ":" + actualPort + "/healthz");
    HttpURLConnection conn = (HttpURLConnection) uri.toURL().openConnection();
    conn.setConnectTimeout(READINESS_HTTP_TIMEOUT_MS);
    conn.setReadTimeout(READINESS_HTTP_TIMEOUT_MS);
    try {
      return conn.getResponseCode() == 200;
    } finally {
      conn.disconnect();
    }
  }

  /**
   * 构建源条目列表，根据 agent 过滤选择用户主目录下的默认源目录。
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
      Path root = Path.of(System.getProperty("user.home"), ".claude");
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new ClaudeSourceAdapter(), root));
      }
    }

    if (includeCodex) {
      Path root = Path.of(System.getProperty("user.home"), ".codex");
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new CodexSourceAdapter(), root));
      }
    }

    if (includeQoder) {
      Path root = Path.of(System.getProperty("user.home"), ".qoder");
      if (Files.isDirectory(root)) {
        entries.add(new ScanConfig.SourceEntry(new QoderSourceAdapter(), root));
      }
    }

    if (entries.isEmpty() && !allowEmpty) {
      throw new IOException("未找到可扫描的源目录，使用 --allow-empty 跳过或使用 --no-scan 禁用扫描");
    }

    return entries;
  }
}
