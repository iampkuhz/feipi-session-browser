package com.feipi.session.browser.contracttest.query.parity;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.DashboardUseCase;
import com.feipi.session.browser.application.ProjectListUseCase;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.DashboardRow;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.ProjectStatsRow;
import com.feipi.session.browser.index.sqlite.SessionDetailRepository;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.index.sqlite.TopProjectRow;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.FailureStatus;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.TitleFilter;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Query Parity 门禁测试。
 *
 * <p>验证 Java 查询结果与 Python queries.py/metrics.py 的等价语义。 使用固定脱敏 DB fixture，逐查询比较 Java 输出与预期值。
 *
 * <p>每个测试用例的 fixture 数据和预期值均手工计算，不依赖 Python 运行时。 如果 Java 查询结果偏离 Python 行为，测试会明确标出差异字段。
 */
@DisplayName("QA-080: Query Parity 门禁 — Java vs Python 等价性")
class QueryParityGateTest {

  @TempDir Path tempDir;
  private IndexConnection ic;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("parity-gate.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(ic.writerConnection());
    insertParityFixture();
  }

  @AfterEach
  void tearDown() {
    if (ic != null) {
      ic.close();
    }
  }

  /**
   * 插入 5 条脱敏 fixture 数据，覆盖多 agent、多项目、多模型场景。
   *
   * <p>数据矩阵：
   *
   * <ul>
   *   <li>s1 — claude_code 项目一 claude-3-opus 10万token 无失败
   *   <li>s2 — claude_code 项目一 claude-3-sonnet 20万token 5次失败
   *   <li>s3 — codex 项目二 gpt-4 30万token 无失败
   *   <li>s4 — qoder 项目二 claude-3-opus 5万token 10次失败
   *   <li>s5 — claude_code 项目三 claude-3-opus 15万token 无失败
   * </ul>
   */
  private void insertParityFixture() throws Exception {
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
              // s1：claude_code 项目一 claude-3-opus
              + " ('cc:s1', 'claude_code', 's1', '会话 Alpha', 'pk1', '项目一', '/a',"
              + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
              + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
              + " 50000, 25000, 15000, 10000, 100000, 0, 0,"
              + " 1704067200, 1704067200, '/f1'),"
              // 会话 s2：claude_code 项目一 claude-3-sonnet 有失败工具
              + " ('cc:s2', 'claude_code', 's2', '会话 Beta', 'pk1', '项目一', '/a',"
              + " '2024-01-02T00:00:00Z', '2024-01-02T02:00:00Z', 7200, 5000, 2000,"
              + " 'claude-3-sonnet', 'main', 'cli', 10, 20, 40,"
              + " 100000, 50000, 30000, 20000, 200000, 5, 1,"
              + " 1704153600, 1704153600, '/f2'),"
              // 会话 s3：codex 项目二 gpt-4
              + " ('cx:s3', 'codex', 's3', '会话 Gamma', 'pk2', '项目二', '/b',"
              + " '2024-01-03T00:00:00Z', '2024-01-03T03:00:00Z', 10800, 8000, 3000,"
              + " 'gpt-4', 'dev', 'vscode', 15, 30, 60,"
              + " 150000, 75000, 45000, 30000, 300000, 0, 0,"
              + " 1704240000, 1704240000, '/f3'),"
              // s4：qoder 项目二 claude-3-opus 有失败工具
              + " ('qd:s4', 'qoder', 's4', '会话 Delta', 'pk2', '项目二', '/b',"
              + " '2024-01-04T00:00:00Z', '2024-01-04T04:00:00Z', 14400, 12000, 4000,"
              + " 'claude-3-opus', 'feature', 'cli', 20, 40, 80,"
              + " 25000, 15000, 10000, 5000, 50000, 10, 2,"
              + " 1704326400, 1704326400, '/f4'),"
              // s5：claude_code 项目三 claude-3-opus
              + " ('cc:s5', 'claude_code', 's5', '会话 Epsilon', 'pk3', '项目三', '/c',"
              + " '2024-01-05T00:00:00Z', '2024-01-05T05:00:00Z', 18000, 15000, 5000,"
              + " 'claude-3-opus', 'main', 'cli', 25, 50, 100,"
              + " 75000, 40000, 20000, 15000, 150000, 0, 0,"
              + " 1704412800, 1704412800, '/f5')");
    }
  }

  @Nested
  @DisplayName("Session 查询 Parity")
  class SessionQueryParity {

    @Test
    @DisplayName("list + count + aggregate 三查询一致性")
    void listCountAggregateConsistency() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);

      SessionListFilter[] filters = {
        SessionListFilter.defaults(),
        SessionListFilter.defaults().withAgent(AgentFilter.of("claude_code")),
        SessionListFilter.defaults().withTitle(TitleFilter.of("会话")),
        SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY),
        SessionListFilter.defaults().withFailureStatus(FailureStatus.SUCCESS_ONLY),
      };

      for (SessionListFilter filter : filters) {
        PageResult<SessionRow> list = repo.listSessions(filter);
        long count = repo.countSessions(filter);
        var agg = repo.listAggregate(filter);

        assertThat(count)
            .as("count 与 list.totalCount 一致: filter=%s", filter)
            .isEqualTo(list.totalCount());
        assertThat(agg.sessionCount())
            .as("aggregate.sessionCount 与 count 一致: filter=%s", filter)
            .isEqualTo(count);
      }
    }

    @Test
    @DisplayName("全量 list 返回 5 行，默认 ended_at DESC 排序")
    void fullListDefaultSort() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      PageResult<SessionRow> result = repo.listSessions(SessionListFilter.defaults());

      assertThat(result.totalCount()).isEqualTo(5);
      assertThat(result.items()).hasSize(5);
      // 默认按 ended_at 降序：s5 > s4 > s3 > s2 > s1
      assertThat(result.items().get(0).sessionKey()).isEqualTo("cc:s5");
      assertThat(result.items().get(4).sessionKey()).isEqualTo("cc:s1");
    }

    @Test
    @DisplayName("agent 过滤：claude_code 返回 3 行")
    void agentFilterClaudeCode() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      var filter = SessionListFilter.defaults().withAgent(AgentFilter.of("claude_code"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.totalCount()).isEqualTo(3);
      assertThat(result.items()).allMatch(r -> r.agent().equals("claude_code"));
    }

    @Test
    @DisplayName("project 过滤：pk2 返回 2 行")
    void projectFilterPk2() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      var filter =
          SessionListFilter.defaults()
              .withProject(com.feipi.session.browser.query.api.ProjectFilter.of("pk2"));
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.totalCount()).isEqualTo(2);
      assertThat(result.items()).allMatch(r -> r.projectKey().equals("pk2"));
    }

    @Test
    @DisplayName("失败状态过滤：FAILED_ONLY 返回 2 行")
    void failedOnlyFilter() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      var filter = SessionListFilter.defaults().withFailureStatus(FailureStatus.FAILED_ONLY);
      PageResult<SessionRow> result = repo.listSessions(filter);

      assertThat(result.totalCount()).isEqualTo(2);
      assertThat(result.items()).allMatch(r -> r.failedToolCount() > 0);
    }

    @Test
    @DisplayName("全量聚合：5 会话、3 项目、800k tokens")
    void fullAggregateParity() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      var agg = repo.listAggregate(SessionListFilter.defaults());

      assertThat(agg.sessionCount()).isEqualTo(5);
      assertThat(agg.projectCount()).isEqualTo(3);
      assertThat(agg.totalTokens()).isEqualTo(800000);
    }
  }

  @Nested
  @DisplayName("Dashboard 查询 Parity")
  class DashboardQueryParity {

    @Test
    @DisplayName("全局 dashboard stats 与 fixture 预期一致")
    void globalDashboardStatsParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardRow stats = repo.dashboardStats(AgentFilter.NONE);

      // 预期值手工计算：
      // 会话总数 = 5
      // claude 3 个 (s1/s2/s5)，codex 1 个 (s3)，qoder 1 个 (s4)
      // 项目数 = 3 (pk1/pk2/pk3)
      // token 总量 = 100k + 200k + 300k + 50k + 150k = 800k
      assertThat(stats.totalSessions()).isEqualTo(5);
      assertThat(stats.claudeSessions()).isEqualTo(3);
      assertThat(stats.codexSessions()).isEqualTo(1);
      assertThat(stats.qoderSessions()).isEqualTo(1);
      assertThat(stats.projectCount()).isEqualTo(3);
      assertThat(stats.totalTokens()).isEqualTo(800000);

      // token 分项
      // 非缓存输入：25k + 50k + 75k + 15k + 40k = 205k
      assertThat(stats.totalFreshInputTokens()).isEqualTo(205000);
      // 输出 token：50k + 100k + 150k + 25k + 75k = 400k
      assertThat(stats.totalOutputTokens()).isEqualTo(400000);
      // 缓存读取：15k + 30k + 45k + 10k + 20k = 120k
      assertThat(stats.totalCacheReadTokens()).isEqualTo(120000);
      // 缓存写入：10k + 20k + 30k + 5k + 15k = 80k
      assertThat(stats.totalCacheWriteTokens()).isEqualTo(80000);

      // 工具与消息
      // 工具调用：20 + 40 + 60 + 80 + 100 = 300
      assertThat(stats.totalToolCalls()).isEqualTo(300);
      // 失败工具：0 + 5 + 0 + 10 + 0 = 15
      assertThat(stats.totalFailedTools()).isEqualTo(15);
      // 用户消息：5 + 10 + 15 + 20 + 25 = 75
      assertThat(stats.totalUserMessages()).isEqualTo(75);
      // 助手消息：10 + 20 + 30 + 40 + 50 = 150
      assertThat(stats.totalAssistantMessages()).isEqualTo(150);
    }

    @Test
    @DisplayName("agent 过滤 dashboard：仅 claude_code")
    void agentFilteredDashboard() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardRow stats = repo.dashboardStats(AgentFilter.of("claude_code"));

      assertThat(stats.totalSessions()).isEqualTo(3);
      assertThat(stats.claudeSessions()).isEqualTo(3);
      assertThat(stats.codexSessions()).isEqualTo(0);
      assertThat(stats.qoderSessions()).isEqualTo(0);
      assertThat(stats.projectCount()).isEqualTo(2); // 项目 pk1 和 pk3
      assertThat(stats.totalTokens()).isEqualTo(450000); // 合计 100k + 200k + 150k
    }
  }

  @Nested
  @DisplayName("项目查询 Parity")
  class ProjectQueryParity {

    @Test
    @DisplayName("项目列表返回 3 个项目")
    void projectListCount() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      PageResult<ProjectStatsRow> result = repo.listProjects(ProjectListFilter.defaults());

      assertThat(result.totalCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("pk1 项目统计与预期一致")
    void pk1ProjectStatsParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      ProjectStatsRow stats = repo.projectStats("pk1");

      // pk1 有 s1 和 s2 两个 claude_code 会话
      assertThat(stats.projectKey()).isEqualTo("pk1");
      assertThat(stats.projectName()).isEqualTo("项目一");
      assertThat(stats.totalSessions()).isEqualTo(2);
      assertThat(stats.claudeSessions()).isEqualTo(2);
      assertThat(stats.totalTokens()).isEqualTo(300000); // 合计 100k + 200k
      assertThat(stats.totalToolCalls()).isEqualTo(60); // 20 + 40
      assertThat(stats.totalFailedTools()).isEqualTo(5); // 0 + 5
    }

    @Test
    @DisplayName("不存在的项目返回零值统计")
    void missingProjectZeroStats() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      ProjectStatsRow stats = repo.projectStats("nonexistent");

      assertThat(stats.totalSessions()).isZero();
      assertThat(stats.totalTokens()).isZero();
      assertThat(stats.totalToolCalls()).isZero();
    }
  }

  @Nested
  @DisplayName("分布与 Top-N Parity")
  class DistributionParity {

    @Test
    @DisplayName("模型分布：3 个模型，claude-3-opus 最多")
    void modelDistributionParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      Map<String, Long> dist = repo.modelDistribution();

      assertThat(dist).hasSize(3);
      assertThat(dist.get("claude-3-opus")).isEqualTo(3); // 会话 s1、s4、s5
      assertThat(dist.get("claude-3-sonnet")).isEqualTo(1); // 会话 s2
      assertThat(dist.get("gpt-4")).isEqualTo(1); // 会话 s3
    }

    @Test
    @DisplayName("Agent 分布：claude_code=3, codex=1, qoder=1")
    void agentDistributionParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      Map<String, Long> dist = repo.agentDistribution();

      assertThat(dist).hasSize(3);
      // 按计数降序
      assertThat(dist.entrySet().iterator().next().getKey()).isEqualTo("claude_code");
      assertThat(dist.get("claude_code")).isEqualTo(3);
      assertThat(dist.get("codex")).isEqualTo(1);
      assertThat(dist.get("qoder")).isEqualTo(1);
    }

    @Test
    @DisplayName("Token 分类统计与 fixture 一致")
    void tokenBreakdownParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      var breakdown = repo.tokenBreakdown();

      assertThat(breakdown.totalFreshInput()).isEqualTo(205000);
      assertThat(breakdown.totalOutput()).isEqualTo(400000);
      assertThat(breakdown.totalCacheRead()).isEqualTo(120000);
      assertThat(breakdown.totalCacheWrite()).isEqualTo(80000);
      assertThat(breakdown.totalToolCalls()).isEqualTo(300);
      assertThat(breakdown.totalFailedTools()).isEqualTo(15);
    }

    @Test
    @DisplayName("Top-2 项目按 token 排序")
    void topProjectsByTokens() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      var top = repo.topProjectsByTokens(2);

      assertThat(top).hasSize(2);
      // pk2 合计 350k，pk1 合计 300k，pk3 合计 150k
      assertThat(top.get(0).projectKey()).isEqualTo("pk2");
      assertThat(top.get(0).totalTokens()).isEqualTo(350000);
      assertThat(top.get(1).projectKey()).isEqualTo("pk1");
      assertThat(top.get(1).totalTokens()).isEqualTo(300000);
    }
  }

  @Nested
  @DisplayName("Use Case 层 Parity")
  class UseCaseParity {

    @Test
    @DisplayName("SessionListUseCase list + anomaly 计数一致")
    void sessionListUseCaseParity() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListUseCase uc = new SessionListUseCase(repo, null, 1);
      var result = uc.listWithAnomalies(SessionListFilter.defaults());

      assertThat(result.page().totalCount()).isEqualTo(5);
      assertThat(result.anomalies()).hasSize(5);
      // anomalies 与 page items 一一对应
      for (int i = 0; i < result.anomalies().size(); i++) {
        assertThat(result.anomalies().get(i).sessionKey())
            .isEqualTo(result.page().items().get(i).sessionKey());
      }
    }

    @Test
    @DisplayName("DashboardUseCase stats 与 repository 一致")
    void dashboardUseCaseParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardUseCase uc = new DashboardUseCase(repo, null, 1);
      DashboardRow stats = uc.stats(AgentFilter.NONE);

      assertThat(stats.totalSessions()).isEqualTo(5);
      assertThat(stats.totalTokens()).isEqualTo(800000);
    }

    @Test
    @DisplayName("ProjectListUseCase list 返回 3 项目")
    void projectListUseCaseParity() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      ProjectListUseCase uc = new ProjectListUseCase(repo, null, 1);
      PageResult<ProjectStatsRow> result = uc.list(ProjectListFilter.defaults());

      assertThat(result.totalCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("SessionDetailUseCase 无制品返回行级详情")
    void sessionDetailUseCaseParity() throws Exception {
      SessionQueryRepository sqRepo = new SessionQueryRepository(ic);
      SessionDetailRepository repo = new SessionDetailRepository(sqRepo);
      SessionDetailUseCase uc = new SessionDetailUseCase(repo, 1);

      var detail = uc.getDetail("cc:s1", PayloadVisibility.STANDARD);
      assertThat(detail).isPresent();
      assertThat(detail.get().sessionRow().sessionKey()).isEqualTo("cc:s1");
      assertThat(detail.get().hasArtifact()).isFalse();
    }
  }

  @Nested
  @DisplayName("跨查询交叉验证")
  class CrossQueryValidation {

    @Test
    @DisplayName("dashboard agent 分布总和 = total_sessions")
    void agentDistributionSumEqualsTotalSessions() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardRow stats = repo.dashboardStats(AgentFilter.NONE);
      Map<String, Long> dist = repo.agentDistribution();

      long sum = dist.values().stream().mapToLong(Long::longValue).sum();
      assertThat(sum).isEqualTo(stats.totalSessions());
    }

    @Test
    @DisplayName("token breakdown 各项总和 = dashboard 对应字段")
    void tokenBreakdownMatchesDashboard() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardRow stats = repo.dashboardStats(AgentFilter.NONE);
      var breakdown = repo.tokenBreakdown();

      assertThat(breakdown.totalFreshInput()).isEqualTo(stats.totalFreshInputTokens());
      assertThat(breakdown.totalOutput()).isEqualTo(stats.totalOutputTokens());
      assertThat(breakdown.totalCacheRead()).isEqualTo(stats.totalCacheReadTokens());
      assertThat(breakdown.totalCacheWrite()).isEqualTo(stats.totalCacheWriteTokens());
      assertThat(breakdown.totalToolCalls()).isEqualTo(stats.totalToolCalls());
      assertThat(breakdown.totalFailedTools()).isEqualTo(stats.totalFailedTools());
    }

    @Test
    @DisplayName("项目 token 总和 = dashboard total_tokens")
    void projectTokenSumMatchesDashboard() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardRow stats = repo.dashboardStats(AgentFilter.NONE);
      var topProjects = repo.topProjectsByTokens(100);

      long projectSum = topProjects.stream().mapToLong(TopProjectRow::totalTokens).sum();
      assertThat(projectSum).isEqualTo(stats.totalTokens());
    }
  }
}
