package com.feipi.session.browser.contracttest.query.performance;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.DashboardUseCase;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.PageRequest;
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
 * 性能基线门禁测试。
 *
 * <p>验证大数据量场景下查询性能满足阶段预算。 使用 500 条 fixture 数据模拟真实负载，测试分页、趋势、聚合和资源预算。
 *
 * <p>性能预算（S4 阶段目标）：
 *
 * <ul>
 *   <li>500 行分页查询 < 200ms（含 count）
 *   <li>500 行聚合查询 < 100ms
 *   <li>Dashboard 全局统计 < 100ms
 *   <li>趋势查询 < 200ms
 *   <li>详情查找 < 50ms
 * </ul>
 *
 * <p>这些预算适用于本地 SQLite WAL 模式，不是云端延迟场景。
 */
@DisplayName("QA-080: 性能基线门禁 — 大数据量查询预算")
class PerformanceBaselineGateTest {

  /** 分页查询性能预算（毫秒）。 */
  private static final long LIST_QUERY_BUDGET_MS = 200;

  /** 聚合查询性能预算（毫秒）。 */
  private static final long AGGREGATE_QUERY_BUDGET_MS = 100;

  /** Dashboard 统计性能预算（毫秒）。 */
  private static final long DASHBOARD_BUDGET_MS = 100;

  /** 趋势查询性能预算（毫秒）。 */
  private static final long TREND_BUDGET_MS = 200;

  /** 详情查找性能预算（毫秒）。 */
  private static final long LOOKUP_BUDGET_MS = 50;

  @TempDir Path tempDir;
  private IndexConnection ic;
  private static final int FIXTURE_SIZE = 500;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("perf-gate.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(ic.writerConnection());
    insertLargeFixture();
  }

  @AfterEach
  void tearDown() {
    if (ic != null) {
      ic.close();
    }
  }

  /**
   * 批量插入 500 条 fixture 数据。
   *
   * <p>数据分布在 10 个项目、3 个 agent、5 个模型。 模拟真实场景的数据倾斜（部分项目会话更多）。
   */
  private void insertLargeFixture() throws Exception {
    String[] agents = {"claude_code", "codex", "qoder"};
    String[] models = {"claude-3-opus", "claude-3-sonnet", "gpt-4", "claude-3.5-sonnet", "o1"};

    try (Statement stmt = ic.writerConnection().createStatement()) {
      // 分批插入，每批 50 行，避免单条 SQL 过大
      for (int batch = 0; batch < FIXTURE_SIZE; batch += 50) {
        StringBuilder values = new StringBuilder();
        int batchSize = Math.min(50, FIXTURE_SIZE - batch);
        for (int j = 0; j < batchSize; j++) {
          int i = batch + j + 1;
          if (j > 0) {
            values.append(",");
          }
          String agent = agents[i % agents.length];
          String model = models[i % models.length];
          // 数据倾斜：pk1 占 30%，pk2 占 20%，其余平均
          String pk;
          String pn;
          if (i % 10 < 3) {
            pk = "pk1";
            pn = "项目一";
          } else if (i % 10 < 5) {
            pk = "pk2";
            pn = "项目二";
          } else {
            int pkIdx = (i % 5) + 3;
            pk = "pk" + pkIdx;
            pn = "项目" + pkIdx;
          }
          int tokens = (i * 1000) % 500000 + 1000;
          int tools = (i * 3) % 200;
          int failed = i % 7 == 0 ? i % 20 : 0;
          int day = (i % 28) + 1;
          int hour = i % 24;

          values.append(
              String.format(
                  " ('perf:s%04d', '%s', 's%04d', '会话 %d', '%s', '%s', '/work',"
                      + " '2024-01-%02dT%02d:00:00Z', '2024-01-%02dT%02d:30:00Z',"
                      + " %d, %d, %d, '%s', 'main', 'cli',"
                      + " %d, %d, %d, %d, %d, %d, %d, %d, %d, 0,"
                      + " 1704067200, 1704067200, '/f%04d')",
                  i,
                  agent,
                  i,
                  i,
                  pk,
                  pn,
                  day,
                  hour,
                  day,
                  hour + 1,
                  1800 + (i % 3600),
                  1500 + (i % 3000),
                  300 + (i % 600),
                  model,
                  i % 50,
                  i % 100,
                  tools,
                  tokens / 3,
                  tokens / 4,
                  tokens / 6,
                  tokens / 12,
                  tokens,
                  failed,
                  i));
        }
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
                + values);
      }
    }
  }

  @Nested
  @DisplayName("分页查询性能")
  class PaginationPerformance {

    @Test
    @DisplayName("500 行 list 分页查询在预算内")
    void listPaginationWithinBudget() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 预热
      repo.listSessions(SessionListFilter.defaults());

      // 测量首页
      long start = System.nanoTime();
      var result =
          repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 50)));
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(result.size()).isEqualTo(50);
      assertThat(result.totalCount()).isEqualTo(FIXTURE_SIZE);
      assertThat(elapsed)
          .as("分页查询应在 %dms 内完成", LIST_QUERY_BUDGET_MS)
          .isLessThan(LIST_QUERY_BUDGET_MS);
    }

    @Test
    @DisplayName("分页偏移不影响性能")
    void paginationOffsetDoesNotDegrade() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 首页
      long start1 = System.nanoTime();
      repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 50)));
      long page1Ms = (System.nanoTime() - start1) / 1_000_000;

      // 第 5 页（offset=200）
      long start2 = System.nanoTime();
      repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(200, 50)));
      long page5Ms = (System.nanoTime() - start2) / 1_000_000;

      // 深分页不应比首页慢 10 倍以上
      assertThat(page5Ms)
          .as("深分页不应显著退化（page1=%dms, page5=%dms）", page1Ms, page5Ms)
          .isLessThan(page1Ms * 10 + 50);
    }

    @Test
    @DisplayName("过滤后分页仍在预算内")
    void filteredPaginationWithinBudget() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      long start = System.nanoTime();
      var result =
          repo.listSessions(
              SessionListFilter.defaults()
                  .withAgent(AgentFilter.of("claude_code"))
                  .withPage(PageRequest.ofOffset(0, 50)));
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(result.totalCount()).isGreaterThan(0);
      assertThat(elapsed).isLessThan(LIST_QUERY_BUDGET_MS);
    }
  }

  @Nested
  @DisplayName("聚合查询性能")
  class AggregatePerformance {

    @Test
    @DisplayName("500 行 count 查询在预算内")
    void countQueryWithinBudget() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 预热
      repo.countSessions(SessionListFilter.defaults());

      long start = System.nanoTime();
      long count = repo.countSessions(SessionListFilter.defaults());
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(count).isEqualTo(FIXTURE_SIZE);
      assertThat(elapsed)
          .as("count 查询应在 %dms 内完成", AGGREGATE_QUERY_BUDGET_MS)
          .isLessThan(AGGREGATE_QUERY_BUDGET_MS);
    }

    @Test
    @DisplayName("500 行 listAggregate 在预算内")
    void listAggregateWithinBudget() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      long start = System.nanoTime();
      var agg = repo.listAggregate(SessionListFilter.defaults());
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(agg.sessionCount()).isEqualTo(FIXTURE_SIZE);
      assertThat(elapsed)
          .as("聚合查询应在 %dms 内完成", AGGREGATE_QUERY_BUDGET_MS)
          .isLessThan(AGGREGATE_QUERY_BUDGET_MS);
    }
  }

  @Nested
  @DisplayName("Dashboard 查询性能")
  class DashboardPerformance {

    @Test
    @DisplayName("Dashboard 全局统计在预算内")
    void dashboardStatsWithinBudget() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      // 预热
      repo.dashboardStats(AgentFilter.NONE);

      long start = System.nanoTime();
      var stats = repo.dashboardStats(AgentFilter.NONE);
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(stats.totalSessions()).isEqualTo(FIXTURE_SIZE);
      assertThat(elapsed)
          .as("Dashboard 统计应在 %dms 内完成", DASHBOARD_BUDGET_MS)
          .isLessThan(DASHBOARD_BUDGET_MS);
    }

    @Test
    @DisplayName("全部 Dashboard 查询在预算内")
    void allDashboardQueriesWithinBudget() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardUseCase uc = new DashboardUseCase(repo, null, 1);

      long totalStart = System.nanoTime();

      uc.stats(AgentFilter.NONE);
      uc.tokenBreakdown();
      uc.modelDistribution();
      uc.agentDistribution();
      uc.aggregateMetrics();
      uc.agentEfficiency();

      long totalElapsed = (System.nanoTime() - totalStart) / 1_000_000;

      // 所有 Dashboard 查询总计应在 1 秒内
      assertThat(totalElapsed).as("全部 Dashboard 查询总计应在 1000ms 内完成").isLessThan(1000);
    }
  }

  @Nested
  @DisplayName("趋势查询性能")
  class TrendPerformance {

    @Test
    @DisplayName("趋势数据查询在预算内")
    void trendDataWithinBudget() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      long start = System.nanoTime();
      // 使用足够大的时间窗口覆盖 fixture 数据（2024-01）
      var trend = repo.trendData(TrendFilter.ofDays(3650));
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(trend).isNotEmpty();
      assertThat(elapsed).as("趋势查询应在 %dms 内完成", TREND_BUDGET_MS).isLessThan(TREND_BUDGET_MS);
    }

    @Test
    @DisplayName("活动趋势查询在预算内")
    void activityTrendWithinBudget() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      long start = System.nanoTime();
      var trend = repo.activityTrend(TrendFilter.ofDays(3650));
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(trend).isNotEmpty();
      assertThat(elapsed).as("活动趋势查询应在 %dms 内完成", TREND_BUDGET_MS).isLessThan(TREND_BUDGET_MS);
    }
  }

  @Nested
  @DisplayName("详情查找性能")
  class LookupPerformance {

    @Test
    @DisplayName("按主键查找在预算内")
    void lookupByKeyWithinBudget() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 预热
      repo.getSession("perf:s0001");

      long start = System.nanoTime();
      var result = repo.getSession("perf:s0250");
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(result).isPresent();
      assertThat(elapsed).as("主键查找应在 %dms 内完成", LOOKUP_BUDGET_MS).isLessThan(LOOKUP_BUDGET_MS);
    }

    @Test
    @DisplayName("不存在的键查找在预算内")
    void missingKeyLookupWithinBudget() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      long start = System.nanoTime();
      var result = repo.getSession("nonexistent:key");
      long elapsed = (System.nanoTime() - start) / 1_000_000;

      assertThat(result).isEmpty();
      assertThat(elapsed).isLessThan(LOOKUP_BUDGET_MS);
    }
  }

  @Nested
  @DisplayName("缓存加速效果")
  class CachePerformance {

    @Test
    @DisplayName("缓存命中比未命中快")
    void cacheHitFasterThanMiss() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      com.feipi.session.browser.application.QueryCache cache =
          new com.feipi.session.browser.application.QueryCache(10);
      SessionListUseCase uc = new SessionListUseCase(repo, cache, 1);

      // 首次查询（缓存未命中）
      long start1 = System.nanoTime();
      uc.listWithAnomalies(SessionListFilter.defaults());
      long missMs = (System.nanoTime() - start1) / 1_000_000;

      // 第二次查询（缓存命中）
      long start2 = System.nanoTime();
      uc.listWithAnomalies(SessionListFilter.defaults());
      long hitMs = (System.nanoTime() - start2) / 1_000_000;

      // 缓存命中应更快或至少不超过 2 倍（允许 GC 抖动）
      assertThat(hitMs)
          .as("缓存命中应更快或相当 (miss=%dms, hit=%dms)", missMs, hitMs)
          .isLessThanOrEqualTo(missMs * 2 + 10);
    }
  }

  @Nested
  @DisplayName("资源预算验证")
  class ResourceBudget {

    @Test
    @DisplayName("大分页不导致内存溢出")
    void largePaginationNoOom() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 请求 limit=500（最大允许值），应安全返回全部数据
      var result =
          repo.listSessions(SessionListFilter.defaults().withPage(PageRequest.ofOffset(0, 500)));

      // 应返回全部 500 行（不超过实际数据量）
      assertThat(result.size()).isEqualTo(FIXTURE_SIZE);
    }

    @Test
    @DisplayName("Top-N limit 限制结果集大小")
    void topNLimitBounded() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var top = repo.topProjectsByTokens(3);
      assertThat(top).hasSizeLessThanOrEqualTo(3);

      var sessions = repo.topSlowestSessions(5);
      assertThat(sessions).hasSizeLessThanOrEqualTo(5);
    }
  }
}
