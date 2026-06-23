package com.feipi.session.browser.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.AggregateQueryRepository;
import com.feipi.session.browser.index.sqlite.DashboardRow;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.ProjectStatsRow;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.index.sqlite.SessionDetailRepository;
import com.feipi.session.browser.index.sqlite.SessionQueryRepository;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectListFilter;
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
 * Use case 集成测试。
 *
 * <p>使用内存 SQLite 验证 use case 端到端行为：组合查询、缓存命中与失效。
 */
@DisplayName("Use case 集成测试")
class UseCaseIntegrationTest {

  @TempDir Path tempDir;
  private IndexConnection ic;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("usecase-test.db");
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
              + " ('cc:s1', 'claude_code', 's1', '会话 Alpha', 'pk1', '项目一', '/a',"
              + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
              + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
              + " 50000, 25000, 15000, 10000, 100000, 0, 0,"
              + " 1704067200, 1704067200, '/f1'),"
              + " ('cc:s2', 'claude_code', 's2', '会话 Beta', 'pk1', '项目一', '/a',"
              + " '2024-01-02T00:00:00Z', '2024-01-02T02:00:00Z', 7200, 5000, 2000,"
              + " 'claude-3-sonnet', 'main', 'cli', 10, 20, 40,"
              + " 100000, 50000, 30000, 20000, 200000, 5, 1,"
              + " 1704153600, 1704153600, '/f2'),"
              + " ('cx:s3', 'codex', 's3', '会话 Gamma', 'pk2', '项目二', '/b',"
              + " '2024-01-03T00:00:00Z', '2024-01-03T03:00:00Z', 10800, 8000, 3000,"
              + " 'gpt-4', 'dev', 'vscode', 15, 30, 60,"
              + " 150000, 75000, 45000, 30000, 300000, 0, 0,"
              + " 1704240000, 1704240000, '/f3')");
    }
  }

  @Nested
  @DisplayName("SessionListUseCase")
  class SessionListUseCaseTests {

    @Test
    @DisplayName("listWithAnomalies 返回分页结果和异常摘要")
    void listWithAnomaliesReturnsPageAndAnomalies() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      QueryCache cache = new QueryCache(10);
      SessionListUseCase uc = new SessionListUseCase(repo, cache, 1);

      var result = uc.listWithAnomalies(SessionListFilter.defaults());
      assertThat(result.page().size()).isEqualTo(3);
      assertThat(result.anomalies()).hasSize(3);
    }

    @Test
    @DisplayName("缓存命中时不重复查询")
    void cacheHitSkipsQuery() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      QueryCache cache = new QueryCache(10);
      SessionListUseCase uc = new SessionListUseCase(repo, cache, 1);

      var r1 = uc.listWithAnomalies(SessionListFilter.defaults());
      var r2 = uc.listWithAnomalies(SessionListFilter.defaults());
      assertThat(r1.page().size()).isEqualTo(r2.page().size());
      assertThat(cache.size()).isEqualTo(1);
    }

    @Test
    @DisplayName("count 与 list 总数一致")
    void countMatchesListTotal() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      SessionListUseCase uc = new SessionListUseCase(repo, null, 1);

      long count = uc.count(SessionListFilter.defaults());
      var result = uc.listWithAnomalies(SessionListFilter.defaults());
      assertThat(count).isEqualTo(result.page().totalCount());
    }
  }

  @Nested
  @DisplayName("ProjectListUseCase")
  class ProjectListUseCaseTests {

    @Test
    @DisplayName("list 返回分页项目列表")
    void listReturnsPage() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      ProjectListUseCase uc = new ProjectListUseCase(repo, null, 1);

      PageResult<ProjectStatsRow> result = uc.list(ProjectListFilter.defaults());
      assertThat(result.size()).isEqualTo(2);
    }

    @Test
    @DisplayName("stats 返回单个项目统计")
    void statsReturnsProjectStats() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      ProjectListUseCase uc = new ProjectListUseCase(repo, null, 1);

      ProjectStatsRow stats = uc.stats("pk1");
      assertThat(stats.projectKey()).isEqualTo("pk1");
      assertThat(stats.totalSessions()).isEqualTo(2);
    }
  }

  @Nested
  @DisplayName("DashboardUseCase")
  class DashboardUseCaseTests {

    @Test
    @DisplayName("stats 返回全局聚合")
    void statsReturnsGlobalAggregate() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      DashboardUseCase uc = new DashboardUseCase(repo, null, 1);

      DashboardRow row = uc.stats(AgentFilter.NONE);
      assertThat(row.totalSessions()).isEqualTo(3);
      assertThat(row.projectCount()).isEqualTo(2);
    }

    @Test
    @DisplayName("缓存加速重复查询")
    void cacheAcceleratesRepeatQuery() throws Exception {
      AggregateQueryRepository repo = new AggregateQueryRepository(ic);
      QueryCache cache = new QueryCache(10);
      DashboardUseCase uc = new DashboardUseCase(repo, cache, 1);

      uc.stats(AgentFilter.NONE);
      uc.stats(AgentFilter.NONE);
      assertThat(cache.size()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("SessionDetailUseCase")
  class SessionDetailUseCaseTests {

    @Test
    @DisplayName("无制品会话返回行级详情")
    void rowOnlyDetailForNoArtifact() throws Exception {
      SessionQueryRepository sqRepo = new SessionQueryRepository(ic);
      SessionDetailRepository repo = new SessionDetailRepository(sqRepo);
      SessionDetailUseCase uc = new SessionDetailUseCase(repo, 1);

      var detail =
          uc.getDetail("cc:s1", com.feipi.session.browser.query.api.PayloadVisibility.STANDARD);
      assertThat(detail).isPresent();
      assertThat(detail.get().sessionRow().sessionKey()).isEqualTo("cc:s1");
      assertThat(detail.get().hasArtifact()).isFalse();
    }

    @Test
    @DisplayName("不存在的会话返回 empty")
    void missingSessionReturnsEmpty() throws Exception {
      SessionQueryRepository sqRepo = new SessionQueryRepository(ic);
      SessionDetailRepository repo = new SessionDetailRepository(sqRepo);
      SessionDetailUseCase uc = new SessionDetailUseCase(repo, 1);

      var detail =
          uc.getDetail(
              "nonexistent", com.feipi.session.browser.query.api.PayloadVisibility.STANDARD);
      assertThat(detail).isEmpty();
    }
  }

  @Nested
  @DisplayName("DiagnosticsUseCase")
  class DiagnosticsUseCaseTests {

    @Test
    @DisplayName("detectWithFilter 过滤指定类型")
    void detectWithFilterByType() throws Exception {
      SessionQueryRepository repo = new SessionQueryRepository(ic);
      DiagnosticsUseCase uc = new DiagnosticsUseCase();

      var filter = com.feipi.session.browser.query.api.SessionListFilter.defaults();
      var page = repo.listSessions(filter);
      var results =
          uc.detectWithFilter(page.items(), com.feipi.session.browser.query.api.AnomalyFilter.NONE);
      assertThat(results).hasSize(3);
    }
  }

  @Nested
  @DisplayName("QueryCompositionRoot")
  class CompositionRootTests {

    @Test
    @DisplayName("root 装配所有 use case")
    void rootAssemblesAllUseCases() {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      assertThat(root.sessionList()).isNotNull();
      assertThat(root.projectList()).isNotNull();
      assertThat(root.dashboard()).isNotNull();
      assertThat(root.sessionDetail()).isNotNull();
      assertThat(root.diagnostics()).isNotNull();
      assertThat(root.cache()).isNull();
    }

    @Test
    @DisplayName("带缓存的 root 可失效")
    void rootWithCacheInvalidates() throws Exception {
      QueryCache cache = new QueryCache(10);
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1), cache);

      root.dashboard().stats(AgentFilter.NONE);
      assertThat(cache.size()).isEqualTo(1);

      root.invalidateCache();
      assertThat(cache.size()).isZero();
    }

    @Test
    @DisplayName("schemaVersion 正确传递")
    void schemaVersionPropagated() {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(5));
      assertThat(root.schemaVersion()).isEqualTo(5);
    }
  }
}
