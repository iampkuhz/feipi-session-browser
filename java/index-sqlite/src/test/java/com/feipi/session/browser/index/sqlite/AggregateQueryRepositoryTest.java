package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.ProjectSortField;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.SortOrder;
import com.feipi.session.browser.query.api.TitleFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link AggregateQueryRepository} 测试。
 *
 * <p>覆盖项目统计、Dashboard 聚合、趋势分析、分布查询、Top-N 排行、衍生指标和空数据库边界。
 */
@DisplayName("AggregateQueryRepository 测试")
class AggregateQueryRepositoryTest {

  @TempDir Path tempDir;

  private IndexConnection indexConnection;
  private AggregateQueryRepository repo;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("test-qa040.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    insertTestData();
    repo = new AggregateQueryRepository(indexConnection);
  }

  private void insertTestData() throws Exception {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name, cwd,"
            + " started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            + " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";

    insertSession(
        sql,
        "claude_code:sess-001",
        "claude_code",
        "sess-001",
        "实现登录功能",
        "proj-alpha",
        "Alpha 项目",
        "/home/user/alpha",
        "2026-06-22T10:00:00Z",
        "2026-06-22T11:00:00Z",
        3600.0,
        3000.0,
        500.0,
        "claude-3-opus",
        10,
        20,
        50,
        100000,
        50000,
        30000,
        20000,
        200000,
        3,
        2);

    insertSession(
        sql,
        "codex:sess-002",
        "codex",
        "sess-002",
        "修复 bug 和优化性能",
        "proj-beta",
        "Beta 项目",
        "/home/user/beta",
        "2026-06-23T09:00:00Z",
        "2026-06-23T10:00:00Z",
        3600.0,
        2500.0,
        800.0,
        "gpt-4",
        5,
        10,
        30,
        80000,
        40000,
        20000,
        10000,
        150000,
        0,
        0);

    insertSession(
        sql,
        "claude_code:sess-003",
        "claude_code",
        "sess-003",
        "Unicode 日本語テスト",
        "proj-alpha",
        "Alpha 项目",
        "/home/user/alpha",
        "2026-06-23T08:00:00Z",
        "2026-06-23T09:30:00Z",
        5400.0,
        4000.0,
        1200.0,
        "claude-3-opus",
        15,
        30,
        80,
        200000,
        100000,
        50000,
        40000,
        390000,
        0,
        1);
  }

  private void insertSession(
      String sql,
      String sessionKey,
      String agent,
      String sessionId,
      String title,
      String projectKey,
      String projectName,
      String cwd,
      String startedAt,
      String endedAt,
      double duration,
      double modelExec,
      double toolExec,
      String model,
      long userMsg,
      long assistantMsg,
      long toolCall,
      long outputTokens,
      long freshInput,
      long cacheRead,
      long cacheWrite,
      long totalTokens,
      long failedTools,
      long subagentCount)
      throws Exception {
    indexConnection
        .writeQueue()
        .submit(
            c -> {
              try (var ps = c.prepareStatement(sql)) {
                ps.setString(1, sessionKey);
                ps.setString(2, agent);
                ps.setString(3, sessionId);
                ps.setString(4, title);
                ps.setString(5, projectKey);
                ps.setString(6, projectName);
                ps.setString(7, cwd);
                ps.setString(8, startedAt);
                ps.setString(9, endedAt);
                ps.setDouble(10, duration);
                ps.setDouble(11, modelExec);
                ps.setDouble(12, toolExec);
                ps.setString(13, model);
                ps.setString(14, "main");
                ps.setString(15, "cli");
                ps.setLong(16, userMsg);
                ps.setLong(17, assistantMsg);
                ps.setLong(18, toolCall);
                ps.setLong(19, outputTokens);
                ps.setLong(20, freshInput);
                ps.setLong(21, cacheRead);
                ps.setLong(22, cacheWrite);
                ps.setLong(23, totalTokens);
                ps.setLong(24, failedTools);
                ps.setLong(25, subagentCount);
                ps.setDouble(26, 1717200000.0);
                ps.setDouble(27, 1717200000.0);
                ps.setString(28, "/path/" + sessionId + ".json");
                ps.executeUpdate();
              }
            })
        .get();
  }

  // ── 项目查询 ──

  @Nested
  @DisplayName("projectStats：单项目聚合")
  class ProjectStats {

    @Test
    @DisplayName("存在的项目返回完整统计")
    void existingProjectReturnsStats() throws Exception {
      ProjectStatsRow row = repo.projectStats("proj-alpha");
      assertThat(row.projectKey()).isEqualTo("proj-alpha");
      assertThat(row.projectName()).isEqualTo("Alpha 项目");
      assertThat(row.totalSessions()).isEqualTo(2);
      assertThat(row.claudeSessions()).isEqualTo(2);
      assertThat(row.codexSessions()).isEqualTo(0);
      assertThat(row.totalTokens()).isEqualTo(590000);
      assertThat(row.totalToolCalls()).isEqualTo(130);
      assertThat(row.totalFailedTools()).isEqualTo(3);
    }

    @Test
    @DisplayName("不存在的项目返回空统计")
    void missingProjectReturnsEmpty() throws Exception {
      ProjectStatsRow row = repo.projectStats("nonexistent");
      assertThat(row.totalSessions()).isEqualTo(0);
      assertThat(row.totalTokens()).isEqualTo(0);
    }

    @Test
    @DisplayName("null projectKey 抛 NullPointerException")
    void nullKeyThrows() {
      assertThatThrownBy(() -> repo.projectStats(null)).isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("countProjects：项目计数")
  class CountProjects {

    @Test
    @DisplayName("默认过滤器返回全部项目数")
    void defaultCount() throws Exception {
      assertThat(repo.countProjects(ProjectListFilter.defaults())).isEqualTo(2);
    }

    @Test
    @DisplayName("搜索过滤器匹配项目名")
    void searchByProjectName() throws Exception {
      ProjectListFilter filter = ProjectListFilter.defaults().withTitle(TitleFilter.of("Alpha"));
      assertThat(repo.countProjects(filter)).isEqualTo(1);
    }

    @Test
    @DisplayName("搜索过滤器匹配 cwd")
    void searchByCwd() throws Exception {
      ProjectListFilter filter = ProjectListFilter.defaults().withTitle(TitleFilter.of("beta"));
      assertThat(repo.countProjects(filter)).isEqualTo(1);
    }

    @Test
    @DisplayName("无匹配返回 0")
    void noMatchReturnsZero() throws Exception {
      ProjectListFilter filter =
          ProjectListFilter.defaults().withTitle(TitleFilter.of("zzz_nonexistent"));
      assertThat(repo.countProjects(filter)).isEqualTo(0);
    }
  }

  @Nested
  @DisplayName("listProjects：项目列表")
  class ListProjects {

    @Test
    @DisplayName("默认排序按最近活跃时间降序")
    void defaultSortByLastActive() throws Exception {
      PageResult<ProjectStatsRow> result = repo.listProjects(ProjectListFilter.defaults());
      assertThat(result.size()).isEqualTo(2);
      assertThat(result.totalCount()).isEqualTo(2);
      // proj-beta 末事件时间更晚，降序排首位
      assertThat(result.items().get(0).projectKey()).isEqualTo("proj-beta");
      assertThat(result.items().get(1).projectKey()).isEqualTo("proj-alpha");
    }

    @Test
    @DisplayName("按 token 总量排序")
    void sortByTotalTokens() throws Exception {
      ProjectListFilter filter =
          ProjectListFilter.defaults()
              .withSort(Sort.ofProject(ProjectSortField.TOTAL_TOKENS, SortOrder.ASC));
      PageResult<ProjectStatsRow> result = repo.listProjects(filter);
      // proj-beta token 总量更小，升序排首位
      assertThat(result.items().get(0).projectKey()).isEqualTo("proj-beta");
    }

    @Test
    @DisplayName("分页 limit=1")
    void paginationLimit() throws Exception {
      ProjectListFilter filter = ProjectListFilter.defaults().withPage(PageRequest.ofOffset(0, 1));
      PageResult<ProjectStatsRow> result = repo.listProjects(filter);
      assertThat(result.size()).isEqualTo(1);
      assertThat(result.totalCount()).isEqualTo(2);
    }

    @Test
    @DisplayName("搜索 + 分页")
    void searchAndPagination() throws Exception {
      ProjectListFilter filter =
          ProjectListFilter.defaults()
              .withTitle(TitleFilter.of("Alpha"))
              .withPage(PageRequest.ofOffset(0, 10));
      PageResult<ProjectStatsRow> result = repo.listProjects(filter);
      assertThat(result.size()).isEqualTo(1);
      assertThat(result.items().get(0).projectKey()).isEqualTo("proj-alpha");
    }
  }

  // ── Dashboard 查询 ──

  @Nested
  @DisplayName("dashboardStats：全局聚合")
  class DashboardStats {

    @Test
    @DisplayName("无过滤返回全部统计")
    void unfilteredDashboard() throws Exception {
      DashboardRow row = repo.dashboardStats(AgentFilter.NONE);
      assertThat(row.totalSessions()).isEqualTo(3);
      assertThat(row.claudeSessions()).isEqualTo(2);
      assertThat(row.codexSessions()).isEqualTo(1);
      assertThat(row.qoderSessions()).isEqualTo(0);
      assertThat(row.projectCount()).isEqualTo(2);
      assertThat(row.totalTokens()).isEqualTo(740000);
      assertThat(row.totalToolCalls()).isEqualTo(160);
      assertThat(row.totalFailedTools()).isEqualTo(3);
    }

    @Test
    @DisplayName("agent 过滤")
    void agentFilteredDashboard() throws Exception {
      DashboardRow row = repo.dashboardStats(AgentFilter.of("claude_code"));
      assertThat(row.totalSessions()).isEqualTo(2);
      assertThat(row.claudeSessions()).isEqualTo(2);
      assertThat(row.codexSessions()).isEqualTo(0);
      assertThat(row.totalTokens()).isEqualTo(590000);
    }
  }

  // ── Token 与分布查询 ──

  @Nested
  @DisplayName("tokenBreakdown：Token 分类统计")
  class TokenBreakdown {

    @Test
    @DisplayName("全表 SUM 聚合正确")
    void fullTableSum() throws Exception {
      TokenBreakdownRow row = repo.tokenBreakdown();
      // 非缓存输入合计：50000 + 40000 + 100000 = 190000
      assertThat(row.totalFreshInput()).isEqualTo(190000);
      // 输出合计：100000 + 80000 + 200000 = 380000
      assertThat(row.totalOutput()).isEqualTo(380000);
      // 缓存读取合计：30000 + 20000 + 50000 = 100000
      assertThat(row.totalCacheRead()).isEqualTo(100000);
      // 缓存写入合计：20000 + 10000 + 40000 = 70000
      assertThat(row.totalCacheWrite()).isEqualTo(70000);
      // 工具调用合计：50 + 30 + 80 = 160
      assertThat(row.totalToolCalls()).isEqualTo(160);
      // 失败工具合计：3 + 0 + 0 = 3
      assertThat(row.totalFailedTools()).isEqualTo(3);
    }
  }

  @Nested
  @DisplayName("分布查询")
  class Distributions {

    @Test
    @DisplayName("模型分布按计数降序")
    void modelDistribution() throws Exception {
      Map<String, Long> dist = repo.modelDistribution();
      // claude-3-opus 出现 2 次，gpt-4 出现 1 次
      assertThat(dist).hasSize(2);
      assertThat(dist).containsEntry("claude-3-opus", 2L);
      assertThat(dist).containsEntry("gpt-4", 1L);
    }

    @Test
    @DisplayName("Agent 分布按计数降序")
    void agentDistribution() throws Exception {
      Map<String, Long> dist = repo.agentDistribution();
      assertThat(dist).containsEntry("claude_code", 2L);
      assertThat(dist).containsEntry("codex", 1L);
      // claude_code 在前
      assertThat(dist.keySet().iterator().next()).isEqualTo("claude_code");
    }

    @Test
    @DisplayName("工具分布返回 top-N 会话")
    void toolDistribution() throws Exception {
      Map<String, AggregateQueryRepository.ToolDistributionEntry> dist = repo.toolDistribution(10);
      assertThat(dist).hasSize(3);
      // sess-003 工具最多（80 次），排在首位
      var first = dist.values().iterator().next();
      assertThat(first.toolCallCount()).isEqualTo(80);
    }

    @Test
    @DisplayName("工具分布 limit=1 只返回一条")
    void toolDistributionLimited() throws Exception {
      Map<String, AggregateQueryRepository.ToolDistributionEntry> dist = repo.toolDistribution(1);
      assertThat(dist).hasSize(1);
    }
  }

  // ── Top-N 查询 ──

  @Nested
  @DisplayName("Top-N 排行")
  class TopN {

    @Test
    @DisplayName("Top 项目按 token 排行")
    void topProjectsByTokens() throws Exception {
      List<TopProjectRow> rows = repo.topProjectsByTokens(10);
      assertThat(rows).hasSize(2);
      assertThat(rows.get(0).projectKey()).isEqualTo("proj-alpha");
      assertThat(rows.get(0).totalTokens()).isEqualTo(590000);
    }

    @Test
    @DisplayName("Top 项目按工具排行")
    void topProjectsByTools() throws Exception {
      List<TopProjectRow> rows = repo.topProjectsByTools(10);
      assertThat(rows).hasSize(2);
      assertThat(rows.get(0).projectKey()).isEqualTo("proj-alpha");
      assertThat(rows.get(0).totalTools()).isEqualTo(130);
    }

    @Test
    @DisplayName("最慢会话按时长排行")
    void topSlowestSessions() throws Exception {
      List<TopSessionRow> rows = repo.topSlowestSessions(10);
      assertThat(rows).hasSize(3);
      // sess-003 时长 5400 秒最长，排在首位
      assertThat(rows.get(0).sessionKey()).isEqualTo("claude_code:sess-003");
      assertThat(rows.get(0).durationSeconds()).isEqualTo(5400.0);
    }

    @Test
    @DisplayName("失败工具会话按失败数排行")
    void topFailedToolSessions() throws Exception {
      List<TopSessionRow> rows = repo.topFailedToolSessions(10);
      // 只有 sess-001 有失败工具
      assertThat(rows).hasSize(1);
      assertThat(rows.get(0).sessionKey()).isEqualTo("claude_code:sess-001");
      assertThat(rows.get(0).failedToolCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("limit 为负数时抛异常")
    void invalidLimitThrows() {
      assertThatThrownBy(() -> repo.topSlowestSessions(0))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }

  // ── 衍生指标 ──

  @Nested
  @DisplayName("aggregateMetrics：聚合衍生指标")
  class AggregateMetrics {

    @Test
    @DisplayName("计算衍生比率")
    void computesDerivedRatios() throws Exception {
      AggregateMetricsRow row = repo.aggregateMetrics();
      // 输入侧总量 = 190000 + 100000 + 70000 = 360000
      assertThat(row.inputSideTotal()).isEqualTo(360000);
      // 总轮次 = 20 + 10 + 30 = 60
      assertThat(row.totalRounds()).isEqualTo(60);
      // 缓存复用比率 = 100000 / 360000 ≈ 0.2778
      assertThat(row.cacheReuseRatio()).isNotNull();
      assertThat(row.cacheReuseRatio()).isEqualTo(0.2778);
      // 缓存写入比率 = 70000 / 360000 ≈ 0.1944
      assertThat(row.cacheWriteRatio()).isNotNull();
      assertThat(row.cacheWriteRatio()).isEqualTo(0.1944);
      // 输出比率 = 380000 / 360000 ≈ 1.0556
      assertThat(row.outputRatio()).isNotNull();
      assertThat(row.outputRatio()).isEqualTo(1.0556);
      // 每轮工具数 = 160 / 60 ≈ 2.67
      assertThat(row.toolsPerRound()).isNotNull();
      assertThat(row.toolsPerRound()).isEqualTo(2.67);
    }
  }

  @Nested
  @DisplayName("agentEfficiency：Agent 效率")
  class AgentEfficiency {

    @Test
    @DisplayName("按 agent + model 分组")
    void groupsByAgentAndModel() throws Exception {
      List<AgentEfficiencyRow> rows = repo.agentEfficiency();
      // claude-3-opus: 2 会话, gpt-4: 1 会话
      assertThat(rows).hasSize(2);
      AgentEfficiencyRow first = rows.get(0);
      assertThat(first.sessionCount()).isEqualTo(2);
      assertThat(first.model()).isEqualTo("claude-3-opus");
    }

    @Test
    @DisplayName("P95 时长正确计算")
    void p95Duration() throws Exception {
      List<AgentEfficiencyRow> rows = repo.agentEfficiency();
      // claude-3-opus 有 2 个会话: 3600.0 和 5400.0
      // P95 最近秩：index = int(0.95 * 1) = 0，排序后首值 = 3600.0
      AgentEfficiencyRow claude =
          rows.stream().filter(r -> r.model().equals("claude-3-opus")).findFirst().orElseThrow();
      assertThat(claude.p95Duration()).isEqualTo(3600.0);
      // 平均时长 = (3600 + 5400) / 2 = 4500.0
      assertThat(claude.avgDuration()).isEqualTo(4500.0);
    }

    @Test
    @DisplayName("缓存复用率计算")
    void cacheReuseRatio() throws Exception {
      List<AgentEfficiencyRow> rows = repo.agentEfficiency();
      AgentEfficiencyRow claude =
          rows.stream().filter(r -> r.model().equals("claude-3-opus")).findFirst().orElseThrow();
      // claude 缓存读取合计 = 30000 + 50000 = 80000
      // claude 输入侧合计 = (50000+30000+20000) + (100000+50000+40000) = 290000
      // 缓存复用比率 = 80000 / 290000 ≈ 0.2759
      assertThat(claude.cacheReuseRatio()).isNotNull();
      assertThat(claude.cacheReuseRatio()).isEqualTo(0.2759);
    }
  }

  // ── 趋势查询 ──

  @Nested
  @DisplayName("trendData：每日趋势")
  class TrendData {

    @Test
    @DisplayName("大时间窗口包含所有测试数据")
    void largeWindowIncludesAll() throws Exception {
      TrendFilter filter = TrendFilter.ofDays(3650);
      List<TrendDayRow> rows = repo.trendData(filter);
      assertThat(rows).isNotEmpty();
      // 所有日期行 total_count 之和等于 3
      long totalCount = rows.stream().mapToLong(TrendDayRow::totalCount).sum();
      assertThat(totalCount).isEqualTo(3);
    }

    @Test
    @DisplayName("agent 过滤趋势数据")
    void agentFilter() throws Exception {
      TrendFilter filter = TrendFilter.defaults().withDays(3650).withAgent(AgentFilter.of("codex"));
      List<TrendDayRow> rows = repo.trendData(filter);
      long totalCount = rows.stream().mapToLong(TrendDayRow::totalCount).sum();
      assertThat(totalCount).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("activityTrend：活动趋势")
  class ActivityTrend {

    @Test
    @DisplayName("大时间窗口包含所有活动数据")
    void largeWindowIncludesAll() throws Exception {
      TrendFilter filter = TrendFilter.ofDays(3650);
      List<ActivityTrendRow> rows = repo.activityTrend(filter);
      assertThat(rows).isNotEmpty();
      // 总 prompt 数 = 10 + 5 + 15 = 30
      long totalPrompts = rows.stream().mapToLong(ActivityTrendRow::totalPrompts).sum();
      assertThat(totalPrompts).isEqualTo(30);
      // 总助手轮次 = 20 + 10 + 30 = 60
      long totalTurns = rows.stream().mapToLong(ActivityTrendRow::assistantTurns).sum();
      assertThat(totalTurns).isEqualTo(60);
    }
  }

  // ── 空数据库边界 ──

  @Nested
  @DisplayName("空数据库边界")
  class EmptyDatabase {

    @Test
    @DisplayName("空库返回全零和空列表")
    void emptyDbReturnsZerosAndEmpty() throws Exception {
      Path emptyDb = tempDir.resolve("empty-qa040.db");
      String jdbcUrl = "jdbc:sqlite:" + emptyDb.toAbsolutePath();
      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      PragmaConfig.DEFAULTS.apply(writerConn);
      try (IndexConnection emptyIc =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl)) {
        IndexSchema.withDefaults().ensureSchema(emptyIc.writerConnection());
        AggregateQueryRepository emptyRepo = new AggregateQueryRepository(emptyIc);

        // 项目统计
        ProjectStatsRow emptyProject = emptyRepo.projectStats("any");
        assertThat(emptyProject.totalSessions()).isEqualTo(0);

        // 项目计数
        assertThat(emptyRepo.countProjects(ProjectListFilter.defaults())).isEqualTo(0);

        // 项目列表
        assertThat(emptyRepo.listProjects(ProjectListFilter.defaults()).isEmpty()).isTrue();

        // Dashboard 全局统计
        DashboardRow dash = emptyRepo.dashboardStats(AgentFilter.NONE);
        assertThat(dash.totalSessions()).isEqualTo(0);
        assertThat(dash.totalTokens()).isEqualTo(0);

        // Token 分类统计
        TokenBreakdownRow tokens = emptyRepo.tokenBreakdown();
        assertThat(tokens.totalFreshInput()).isEqualTo(0);

        // 分布查询
        assertThat(emptyRepo.modelDistribution()).isEmpty();
        assertThat(emptyRepo.agentDistribution()).isEmpty();
        assertThat(emptyRepo.toolDistribution(10)).isEmpty();

        // Top-N 排行
        assertThat(emptyRepo.topProjectsByTokens(10)).isEmpty();
        assertThat(emptyRepo.topSlowestSessions(10)).isEmpty();
        assertThat(emptyRepo.topFailedToolSessions(10)).isEmpty();
        assertThat(emptyRepo.topHighCacheReadSessions(10)).isEmpty();

        // 衍生指标
        AggregateMetricsRow metrics = emptyRepo.aggregateMetrics();
        assertThat(metrics.inputSideTotal()).isEqualTo(0);
        assertThat(metrics.cacheReuseRatio()).isNull();
        assertThat(metrics.toolsPerRound()).isNull();

        // Agent 效率
        assertThat(emptyRepo.agentEfficiency()).isEmpty();

        // 趋势
        TrendFilter tf = TrendFilter.ofDays(30);
        assertThat(emptyRepo.trendData(tf)).isEmpty();
        assertThat(emptyRepo.activityTrend(tf)).isEmpty();
      }
    }
  }
}
