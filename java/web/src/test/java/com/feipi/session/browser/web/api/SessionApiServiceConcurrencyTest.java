package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.index.api.write.MissingTranscriptSession;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * SessionApiService 并发缓存测试。
 *
 * <p>验证版本化缓存机制在并发场景下的正确性： - invalidateCache() 后旧版本缓存被失效 - 并发请求不会导致旧数据重新填充 - 新版本请求返回最新数据
 */
@DisplayName("SessionApiService 并发缓存测试")
class SessionApiServiceConcurrencyTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;
  private SqliteIndexWriter writer;
  private SessionDetailUseCase detailUseCase;
  private SessionApiService service;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("cache-concurrency-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    writer = new SqliteIndexWriter(indexConnection.writerConnection());

    QueryCompositionRoot queryRoot =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    detailUseCase = queryRoot.sessionDetail();
    service = new SessionApiService(detailUseCase);
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("并发请求在 invalidateCache 后看到最新数据")
  void concurrentRequestsAfterInvalidationSeeFreshData() throws Exception {
    // 准备：写入初始数据
    String sessionKey = "claude_code:session-1";
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-1",
            "Old Title",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    // 第一次请求，缓存数据
    Optional<SessionApiService.SessionApiContext> ctx1 =
        service.getContext(sessionKey, PayloadVisibility.FULL);
    assertThat(ctx1).isPresent();
    assertThat(ctx1.get().sessionRow().title()).isEqualTo("Old Title");

    // 更新数据
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-1",
            "New Title",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    // 失效缓存
    service.invalidateCache();

    // 并发请求：多个线程同时请求
    int threadCount = 10;
    ExecutorService executor = Executors.newFixedThreadPool(threadCount);
    CountDownLatch startLatch = new CountDownLatch(1);
    CountDownLatch doneLatch = new CountDownLatch(threadCount);
    AtomicInteger successCount = new AtomicInteger(0);

    for (int i = 0; i < threadCount; i++) {
      executor.submit(
          () -> {
            try {
              startLatch.await(); // 等待所有线程同时开始
              Optional<SessionApiService.SessionApiContext> ctx =
                  service.getContext(sessionKey, PayloadVisibility.FULL);
              if (ctx.isPresent() && ctx.get().sessionRow().title().equals("New Title")) {
                successCount.incrementAndGet();
              }
            } catch (Exception e) {
              // 忽略异常
            } finally {
              doneLatch.countDown();
            }
          });
    }

    // 同时启动所有线程
    startLatch.countDown();

    // 等待完成
    boolean completed = doneLatch.await(5, TimeUnit.SECONDS);
    executor.shutdown();
    executor.awaitTermination(5, TimeUnit.SECONDS);

    // 验证：所有并发请求都应该看到新数据
    assertThat(completed).isTrue();
    assertThat(successCount.get()).isEqualTo(threadCount);
  }

  @Test
  @DisplayName("缓存版本防止旧数据重新填充")
  void cacheVersionPreventsStaleRepopulation() throws Exception {
    String sessionKey = "claude_code:session-2";

    // 写入第一版本
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-2",
            "Version 1",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    Optional<SessionApiService.SessionApiContext> ctx1 =
        service.getContext(sessionKey, PayloadVisibility.FULL);
    assertThat(ctx1).isPresent();
    assertThat(ctx1.get().sessionRow().title()).isEqualTo("Version 1");

    // 失效缓存
    service.invalidateCache();

    // 写入第二版本
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-2",
            "Version 2",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    // 再次请求，应该看到新数据
    Optional<SessionApiService.SessionApiContext> ctx2 =
        service.getContext(sessionKey, PayloadVisibility.FULL);
    assertThat(ctx2).isPresent();
    assertThat(ctx2.get().sessionRow().title()).isEqualTo("Version 2");

    // 再次失效
    service.invalidateCache();

    // 写入第三版本
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-2",
            "Version 3",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    // 应该看到最新版本
    Optional<SessionApiService.SessionApiContext> ctx3 =
        service.getContext(sessionKey, PayloadVisibility.FULL);
    assertThat(ctx3).isPresent();
    assertThat(ctx3.get().sessionRow().title()).isEqualTo("Version 3");
  }

  @Test
  @DisplayName("多次 invalidateCache 递增版本号")
  void multipleInvalidationsIncrementVersion() throws Exception {
    String sessionKey = "claude_code:session-3";

    // 写入初始数据
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-3",
            "Initial",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    // 初始请求
    service.getContext(sessionKey, PayloadVisibility.FULL);

    // 多次失效
    service.invalidateCache();
    service.invalidateCache();
    service.invalidateCache();

    // 写入新数据
    writer.writeMissingTranscriptSession(
        new MissingTranscriptSession(
            sessionKey,
            "claude_code",
            "session-3",
            "After Invalidations",
            "/project",
            "project",
            "/cwd",
            Instant.now().toString(),
            "claude-3",
            "claude_code",
            Instant.now()));
    writer.flushPendingWrites();

    // 应该看到最新数据
    Optional<SessionApiService.SessionApiContext> ctx =
        service.getContext(sessionKey, PayloadVisibility.FULL);
    assertThat(ctx).isPresent();
    assertThat(ctx.get().sessionRow().title()).isEqualTo("After Invalidations");
  }
}
