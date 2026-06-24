package com.feipi.session.browser.contracttest.query.readonly;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.DashboardUseCase;
import com.feipi.session.browser.application.ProjectListUseCase;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.ReadTransaction;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 只读保证门禁测试。
 *
 * <p>验证所有查询路径使用 {@link ReadTransaction} 的独立连接，不在 writer 连接上执行查询。 只读保证是架构级的：查询方法通过 {@code
 * indexConnection.readTransaction()} 创建独立连接， 查询完成后自动关闭，不与 writer 连接共享状态。
 *
 * <p>测试策略：
 *
 * <ul>
 *   <li>ReadTransaction 使用独立连接，非 writer 连接。
 *   <li>执行所有查询后数据库内容不变。
 *   <li>ReadTransaction 关闭后连接已关闭。
 *   <li>每次 readTransaction 创建新连接。
 * </ul>
 */
@DisplayName("QA-080: 只读保证门禁 — 查询连接无 DDL/DML")
class ReadOnlyGateTest {

  @TempDir Path tempDir;
  private IndexConnection ic;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("readonly-gate.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(ic.writerConnection());
    insertFixtures();
  }

  @AfterEach
  void tearDown() {
    if (ic != null) {
      ic.close();
    }
  }

  private void insertFixtures() throws Exception {
    try (Statement stmt = ic.writerConnection().createStatement()) {
      stmt.execute(
          "INSERT INTO sessions"
              + " (session_key, agent, session_id, title, project_key, project_name,"
              + " cwd, started_at, ended_at, duration_seconds, model_execution_seconds,"
              + " tool_execution_seconds, model, git_branch, source,"
              + " user_message_count, assistant_message_count, tool_call_count,"
              + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
              + " total_tokens, failed_tool_count, subagent_instance_count,"
              + " indexed_at, file_mtime, file_path)"
              + " VALUES"
              + " ('cc:s1', 'claude_code', 's1', '只读测试', 'pk1', '项目一', '/a',"
              + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
              + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
              + " 50000, 25000, 15000, 10000, 100000, 0, 0,"
              + " 1704067200, 1704067200, '/f1')");
    }
  }

  /** 获取当前 sessions 表的行数。 */
  private long getRowCount() throws Exception {
    try (Statement stmt = ic.writerConnection().createStatement();
        var rs = stmt.executeQuery("SELECT COUNT(*) FROM sessions")) {
      rs.next();
      return rs.getLong(1);
    }
  }

  /** 获取 sessions 表 checksum，验证数据内容未被修改。 */
  private long getDataChecksum() throws Exception {
    try (Statement stmt = ic.writerConnection().createStatement();
        var rs =
            stmt.executeQuery(
                "SELECT COALESCE(SUM(total_tokens + tool_call_count * 7"
                    + " + user_message_count * 13), 0) FROM sessions")) {
      rs.next();
      return rs.getLong(1);
    }
  }

  @Nested
  @DisplayName("ReadTransaction 连接隔离")
  class ReadTransactionIsolation {

    @Test
    @DisplayName("ReadTransaction 使用独立连接，不共享 writer 连接")
    void readTransactionUsesIndependentConnection() throws Exception {
      Connection writerConn = ic.writerConnection();

      try (ReadTransaction rt = ic.readTransaction()) {
        Connection readConn = rt.connection();
        // 读连接不应是 writer 连接
        assertThat(readConn).isNotSameAs(writerConn);
        // ReadTransaction 关闭了 auto-commit 开启事务
        assertThat(readConn.getAutoCommit()).isFalse();
      }
    }

    @Test
    @DisplayName("ReadTransaction 关闭后连接已关闭")
    void readTransactionClosedConnectionClosed() throws Exception {
      ReadTransaction rt = ic.readTransaction();
      Connection readConn = rt.connection();
      assertThat(readConn.isClosed()).isFalse();

      rt.close();
      assertThat(readConn.isClosed()).isTrue();
    }

    @Test
    @DisplayName("每次 readTransaction 创建新连接")
    void eachReadTransactionCreatesNewConnection() throws Exception {
      ReadTransaction rt1 = ic.readTransaction();
      ReadTransaction rt2 = ic.readTransaction();

      assertThat(rt1.connection()).isNotSameAs(rt2.connection());

      rt1.close();
      rt2.close();
    }

    @Test
    @DisplayName("ReadTransaction 关闭是幂等操作")
    void readTransactionCloseIsIdempotent() throws Exception {
      ReadTransaction rt = ic.readTransaction();
      rt.close();
      // 第二次关闭不抛异常
      rt.close();
      assertThat(rt.connection().isClosed()).isTrue();
    }
  }

  @Nested
  @DisplayName("查询方法数据完整性")
  class QueryMethodIntegrity {

    @Test
    @DisplayName("SessionQueryRepository 全部查询不修改数据")
    void sessionQueryRepositoryReadOnly() throws Exception {
      long rowCountBefore = getRowCount();
      long checksumBefore = getDataChecksum();

      SessionQueryRepository repo = new SessionQueryRepository(ic);
      repo.getSession("cc:s1");
      repo.listSessions(SessionListFilter.defaults());
      repo.countSessions(SessionListFilter.defaults());
      repo.listAggregate(SessionListFilter.defaults());
      // 分页查询
      repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 1)));

      assertThat(getRowCount()).as("查询后行数不变").isEqualTo(rowCountBefore);
      assertThat(getDataChecksum()).as("查询后数据校验和不变").isEqualTo(checksumBefore);
    }

    @Test
    @DisplayName("AggregateQueryRepository 全部查询不修改数据")
    void aggregateQueryRepositoryReadOnly() throws Exception {
      long rowCountBefore = getRowCount();
      long checksumBefore = getDataChecksum();

      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      repo.dashboardStats(AgentFilter.NONE);
      repo.projectStats("pk1");
      repo.listProjects(ProjectListFilter.defaults());
      repo.countProjects(ProjectListFilter.defaults());
      repo.tokenBreakdown();
      repo.modelDistribution();
      repo.agentDistribution();
      repo.toolDistribution(10);
      repo.topProjectsByTokens(5);
      repo.topProjectsByTools(5);
      repo.topSlowestSessions(5);
      repo.topFailedToolSessions(5);
      repo.topHighCacheReadSessions(5);
      repo.aggregateMetrics();
      repo.agentEfficiency();
      repo.trendData(TrendFilter.defaults());
      repo.activityTrend(TrendFilter.defaults());

      assertThat(getRowCount()).as("查询后行数不变").isEqualTo(rowCountBefore);
      assertThat(getDataChecksum()).as("查询后数据校验和不变").isEqualTo(checksumBefore);
    }

    @Test
    @DisplayName("Use Case 层查询不修改数据")
    void useCaseLayerReadOnly() throws Exception {
      long rowCountBefore = getRowCount();
      long checksumBefore = getDataChecksum();

      SessionQueryRepository sqRepo = new SessionQueryRepository(ic);
      AggregateQueryRepository aggRepo = new AggregateQueryRepository(ic);

      SessionListUseCase sessionUc = new SessionListUseCase(sqRepo, null, 1);
      DashboardUseCase dashboardUc = new DashboardUseCase(aggRepo, null, 1);
      ProjectListUseCase projectUc = new ProjectListUseCase(aggRepo, null, 1);

      sessionUc.listWithAnomalies(SessionListFilter.defaults());
      sessionUc.count(SessionListFilter.defaults());
      dashboardUc.stats(AgentFilter.NONE);
      dashboardUc.tokenBreakdown();
      dashboardUc.modelDistribution();
      projectUc.list(ProjectListFilter.defaults());
      projectUc.stats("pk1");

      assertThat(getRowCount()).as("查询后行数不变").isEqualTo(rowCountBefore);
      assertThat(getDataChecksum()).as("查询后数据校验和不变").isEqualTo(checksumBefore);
    }
  }

  @Nested
  @DisplayName("并发读安全性")
  class ConcurrentReadSafety {

    @Test
    @DisplayName("多线程并发读不互相干扰，数据完整")
    void concurrentReadsDontInterfere() throws Exception {
      Path dbFile = tempDir.resolve("readonly-gate.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Thread[] threads = new Thread[4];
      Exception[] errors = new Exception[1];

      for (int i = 0; i < threads.length; i++) {
        final int threadIdx = i;
        threads[i] =
            new Thread(
                () -> {
                  try {
                    Connection conn = DriverManager.getConnection(jdbcUrl);
                    PragmaConfig.DEFAULTS.apply(conn);
                    IndexConnection localIc =
                        IndexConnection.create(conn, PragmaConfig.DEFAULTS, jdbcUrl);
                    SessionQueryRepository localRepo = new SessionQueryRepository(localIc);

                    for (int j = 0; j < 10; j++) {
                      localRepo.getSession("cc:s1");
                      var result = localRepo.listSessions(SessionListFilter.defaults());
                      assertThat(result.totalCount()).isEqualTo(1);
                    }

                    localIc.close();
                  } catch (Exception e) {
                    errors[0] = e;
                  }
                });
        threads[i].start();
      }

      for (Thread t : threads) {
        t.join(10000);
      }

      assertThat(errors[0]).isNull();
      // 原始数据仍然完整
      assertThat(getRowCount()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("缓存不引入写副作用")
  class CacheReadOnlySideEffect {

    @Test
    @DisplayName("缓存命中/失效不修改数据库")
    void cacheOperationsDoNotModifyDatabase() throws Exception {
      long rowCountBefore = getRowCount();

      SessionQueryRepository sqRepo = new SessionQueryRepository(ic);
      com.feipi.session.browser.application.QueryCache cache =
          new com.feipi.session.browser.application.QueryCache(10);
      SessionListUseCase uc = new SessionListUseCase(sqRepo, cache, 1);

      // 填充缓存
      uc.listWithAnomalies(SessionListFilter.defaults());
      assertThat(cache.size()).isEqualTo(1);

      // 缓存命中
      uc.listWithAnomalies(SessionListFilter.defaults());
      assertThat(cache.size()).isEqualTo(1);

      // 缓存失效
      cache.invalidateAll();
      assertThat(cache.size()).isZero();

      // 数据库不变
      assertThat(getRowCount()).isEqualTo(rowCountBefore);
    }
  }
}
