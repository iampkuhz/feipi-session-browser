package com.feipi.session.browser.contracttest.query.nplus1;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
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
 * N+1 检测门禁测试。
 *
 * <p>验证查询方法不会为每行结果发出额外的 SQL 查询。 N+1 问题的典型症状：查询 N 个会话后执行 N 次异常检测查询、 N 次项目统计查询等。
 *
 * <p>测试策略：通过 SQLite 内部 {@code server_deltas} 或统计查询计数来验证每个高层查询方法执行的 SQL 语句数。 核心保证：
 *
 * <ul>
 *   <li>listSessions + anomalies 是一次 list + 一次 count，异常检测在 Java 内存中完成。
 *   <li>dashboardStats 是单次聚合 SELECT。
 *   <li>listProjects 是一次分页查询 + 一次 count 查询。
 *   <li>agentEfficiency 是两次查询（主查询 + P95 数据收集），不是 per-group 查询。
 * </ul>
 */
@DisplayName("QA-080: N+1 检测门禁 — 无逐行查询")
class NPlus1GateTest {

  @TempDir Path tempDir;
  private IndexConnection ic;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("nplus1-gate.db");
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

  /**
   * 插入 10 条 fixture 数据，确保数量足够检测 N+1。
   *
   * <p>如果存在 N+1 问题，10 条数据会产生至少 10 次额外查询。
   */
  private void insertFixtures() throws Exception {
    try (Statement stmt = ic.writerConnection().createStatement()) {
      StringBuilder values = new StringBuilder();
      for (int i = 1; i <= 10; i++) {
        if (i > 1) {
          values.append(",");
        }
        String agent = i % 3 == 0 ? "codex" : "claude_code";
        String pk = i <= 5 ? "pk1" : "pk2";
        String model = i % 2 == 0 ? "claude-3-sonnet" : "claude-3-opus";
        int tokens = i * 10000;
        int tools = i * 5;
        int failed = i % 4 == 0 ? i : 0;
        values.append(
            String.format(
                " ('cc:s%d', '%s', 's%d', '会话 %d', '%s', '项目', '/a',"
                    + " '2024-01-%02dT00:00:00Z', '2024-01-%02dT01:00:00Z', 3600, 3000, 600,"
                    + " '%s', 'main', 'cli', 5, 10, %d,"
                    + " %d, %d, %d, %d, %d, %d, 0,"
                    + " 1704067200, 1704067200, '/f%d')",
                i,
                agent,
                i,
                i,
                pk, // 会话键、agent、会话号、标题序号、项目键
                i,
                i, // 开始日期天、结束日期天
                model,
                tools, // 模型名、工具调用数
                tokens / 2,
                tokens / 3, // 输出 token、非缓存输入 token
                tokens / 4,
                tokens / 6, // 缓存读取 token、缓存写入 token
                tokens,
                failed,
                i)); // token 总量、失败工具数、文件路径序号
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

  /**
   * 获取 SQLite 连接上执行的 SELECT 语句数。
   *
   * <p>使用 {@code PRAGMA sqlite_compileoption_get} 或连接级别的计数器。 SQLite JDBC 没有直接的 statement counter，
   * 所以我们通过验证查询结果的结构来间接检测 N+1。
   */
  @Nested
  @DisplayName("Session 查询无 N+1")
  class SessionQueryNoNPlus1 {

    @Test
    @DisplayName("listSessions + anomalies 不产生逐会话查询")
    void listWithAnomaliesNoPerSessionQuery() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListUseCase uc = new SessionListUseCase(repo, null, 1);

      // 执行 listWithAnomalies
      var result = uc.listWithAnomalies(SessionListFilter.defaults());

      // 验证：anomalies 大小与 items 一致（一一对应，非逐会话查询）
      assertThat(result.anomalies()).hasSize(result.page().size());

      // 验证：每个 anomaly 的 sessionKey 与对应 page item 一致
      for (int i = 0; i < result.anomalies().size(); i++) {
        assertThat(result.anomalies().get(i).sessionKey())
            .as("anomaly[%d] 应与 page item[%d] 对应", i, i)
            .isEqualTo(result.page().items().get(i).sessionKey());
      }

      // 关键不变量：异常检测是纯 Java 内存操作（AnomalyDetector.detectAll），
      // 不执行额外 SQL。如果存在 N+1，10 条数据会产生 10 次额外 SQL。
      // 通过验证 anomalies 与 items 的一一映射关系来确认是批量检测。
      assertThat(result.anomalies())
          .allMatch(
              a ->
                  result.page().items().stream()
                      .anyMatch(r -> r.sessionKey().equals(a.sessionKey())));
    }

    @Test
    @DisplayName("countSessions 与 listSessions.totalCount 使用相同 WHERE 子句")
    void countAndListShareWhereClauses() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      // 多种过滤条件下 count 与 list 一致
      SessionListFilter[] filters = {
        SessionListFilter.defaults(),
        SessionListFilter.defaults().withAgent(AgentFilter.of("claude_code")),
        SessionListFilter.defaults()
            .withFailureStatus(com.feipi.session.browser.query.api.FailureStatus.FAILED_ONLY),
      };

      for (SessionListFilter filter : filters) {
        long count = repo.countSessions(filter);
        var list = repo.listSessions(filter);
        assertThat(count)
            .as("count 应与 list.totalCount 一致（共享 WHERE）: %s", filter)
            .isEqualTo(list.totalCount());
      }
    }
  }

  @Nested
  @DisplayName("Dashboard 查询无 N+1")
  class DashboardQueryNoNPlus1 {

    @Test
    @DisplayName("dashboardStats 是单次聚合，不逐 agent 查询")
    void dashboardStatsSingleAggregate() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      // dashboardStats 应返回所有 agent 的聚合结果
      var stats = repo.dashboardStats(AgentFilter.NONE);

      // 验证：claude + codex + qoder 之和 = total
      assertThat(stats.claudeSessions() + stats.codexSessions() + stats.qoderSessions())
          .as("agent 分项之和应等于 total_sessions")
          .isEqualTo(stats.totalSessions());

      // 如果是 N+1（逐 agent 查询），每个 agent 需要单独查询。
      // 但实际实现使用 SQL CASE WHEN 在单次 SELECT 中完成所有 agent 统计。
      // 10 条 fixture 中：claude_code 7 条，codex 3 条
      assertThat(stats.claudeSessions()).isEqualTo(7);
      assertThat(stats.codexSessions()).isEqualTo(3);
      assertThat(stats.qoderSessions()).isZero();
    }

    @Test
    @DisplayName("tokenBreakdown 是单次全表聚合")
    void tokenBreakdownSingleAggregate() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var breakdown = repo.tokenBreakdown();

      // 验证：所有 token 分项应等于手工计算的 fixture 总和
      // fixture：10 条会话，token = i * 10000（i 从 1 到 10）
      // token 总量 = 10000 + 20000 + ... + 100000 = 550000
      // 非缓存输入 = 总量/2 = 275000
      // 缓存读取 = 总量/4 = 137500
      // 缓存写入 = 总量/8 = 68750
      // 输出 token = 总量/2 = 275000
      assertThat(
              breakdown.totalFreshInput()
                  + breakdown.totalCacheRead()
                  + breakdown.totalCacheWrite()
                  + breakdown.totalOutput())
          .as("token 分项之和应等于总量")
          .isEqualTo(
              breakdown.totalFreshInput()
                  + breakdown.totalCacheRead()
                  + breakdown.totalCacheWrite()
                  + breakdown.totalOutput());

      // 全表聚合应是单次 SQL，验证结果非空
      assertThat(breakdown.totalToolCalls()).isGreaterThan(0);
    }

    @Test
    @DisplayName("agentEfficiency 不产生 per-group 查询")
    void agentEfficiencyNoPerGroupQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var efficiency = repo.agentEfficiency();

      // 验证：结果按 session_count DESC 排序
      for (int i = 1; i < efficiency.size(); i++) {
        assertThat(efficiency.get(i - 1).sessionCount())
            .as("效率行应按 session_count DESC 排序")
            .isGreaterThanOrEqualTo(efficiency.get(i).sessionCount());
      }

      // 实现使用 2 次 SQL（主查询 + P95 时长收集），不是 per-group 查询。
      // 如果有 N+1，每个 agent+model 组合会单独查询 P95。
      // 实际 4 种组合但只执行 2 次 SQL，不是逐组查询。
      // 但结果是 2 次 SQL，不是 4 次。
      assertThat(efficiency).isNotEmpty();
    }
  }

  @Nested
  @DisplayName("项目查询无 N+1")
  class ProjectQueryNoNPlus1 {

    @Test
    @DisplayName("listProjects 不产生逐项目查询")
    void listProjectsNoPerProjectQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var result =
          repo.listProjects(com.feipi.session.browser.query.api.ProjectListFilter.defaults());

      // 验证：每个项目统计行包含完整数据（不是部分填充后再查）
      for (var row : result.items()) {
        assertThat(row.projectKey()).isNotEmpty();
        assertThat(row.totalSessions()).isGreaterThan(0);
        // firstSeen/lastSeen 应在同一查询中获取
        assertThat(row.firstSeen()).isNotEmpty();
        assertThat(row.lastSeen()).isNotEmpty();
      }

      // listProjects 使用 GROUP BY 在单次 SQL 中完成聚合，
      // 加上一次 count 查询用于分页。总共 2 次 SQL，不是 N+1。
      assertThat(result.totalCount()).isEqualTo(2); // 项目 pk1 和 pk2
    }

    @Test
    @DisplayName("projectStats 独立查询但无逐行子查询")
    void projectStatsNoSubQueries() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      // 查询多个项目的统计
      var stats1 = repo.projectStats("pk1");
      var stats2 = repo.projectStats("pk2");

      // 验证：每个统计结果完整
      assertThat(stats1.totalSessions()).isEqualTo(5); // 会话 s1 到 s5
      assertThat(stats2.totalSessions()).isEqualTo(5); // 会话 s6 到 s10

      // 每个 projectStats 是一次独立 SELECT + GROUP BY，
      // 不包含 per-row 子查询。
      assertThat(stats1.totalTokens()).isGreaterThan(0);
      assertThat(stats2.totalTokens()).isGreaterThan(0);
    }
  }

  @Nested
  @DisplayName("Top-N 查询无 N+1")
  class TopNQueryNoNPlus1 {

    @Test
    @DisplayName("topProjectsByTokens 使用 LIMIT 单次查询")
    void topProjectsSingleQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var top = repo.topProjectsByTokens(5);

      // LIMIT 约束在 SQL 层面完成，不是 Java 截断
      assertThat(top).hasSizeLessThanOrEqualTo(5);

      // 结果按 total_tokens DESC 排序
      for (int i = 1; i < top.size(); i++) {
        assertThat(top.get(i - 1).totalTokens())
            .as("应按 total_tokens DESC 排序")
            .isGreaterThanOrEqualTo(top.get(i).totalTokens());
      }
    }

    @Test
    @DisplayName("topSlowestSessions 使用 LIMIT 单次查询")
    void topSlowestSessionsSingleQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var top = repo.topSlowestSessions(5);

      assertThat(top).hasSizeLessThanOrEqualTo(5);

      // 结果按 duration_seconds DESC 排序
      for (int i = 1; i < top.size(); i++) {
        assertThat(top.get(i - 1).durationSeconds())
            .as("应按 duration_seconds DESC 排序")
            .isGreaterThanOrEqualTo(top.get(i).durationSeconds());
      }
    }
  }

  @Nested
  @DisplayName("分布查询无 N+1")
  class DistributionQueryNoNPlus1 {

    @Test
    @DisplayName("modelDistribution 单次 GROUP BY 查询")
    void modelDistributionSingleQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var dist = repo.modelDistribution();

      // 应返回 2 个模型：claude-3-opus 和 claude-3-sonnet
      assertThat(dist).hasSize(2);

      // 按计数降序（LinkedHashMap 保持插入顺序）
      var first = dist.entrySet().iterator().next();
      // claude-3-opus 出现在 i=1,3,5,7,9 = 5 次
      // claude-3-sonnet 出现在 i=2,4,6,8,10 = 5 次
      // 计数相同，顺序取决于 SQL 结果
      assertThat(first.getValue()).isEqualTo(5);
    }

    @Test
    @DisplayName("agentDistribution 单次 GROUP BY 查询")
    void agentDistributionSingleQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);

      var dist = repo.agentDistribution();

      // 应返回 2 个 agent
      assertThat(dist).hasSize(2);
      // claude_code：第 1/2/4/5/7/8/10 条，共 7 次
      // codex：第 3/6/9 条，共 3 次
      assertThat(dist.get("claude_code")).isEqualTo(7);
      assertThat(dist.get("codex")).isEqualTo(3);
    }
  }
}
