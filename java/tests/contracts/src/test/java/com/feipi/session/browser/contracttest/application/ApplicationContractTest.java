package com.feipi.session.browser.contracttest.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
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
 * Application use case 契约测试。
 *
 * <p>验证 composition root 装配、缓存失效和端到端查询语义。
 */
@DisplayName("Application use case 契约测试")
class ApplicationContractTest {

  @TempDir Path tempDir;
  private IndexConnection ic;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("contract-qa070.db");
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
              + " ('cc:s1', 'claude_code', 's1', '测试会话', 'pk1', '测试项目', '/work',"
              + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
              + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
              + " 50000, 25000, 15000, 10000, 100000, 0, 0,"
              + " 1704067200, 1704067200, '/f1')");
    }
  }

  @Nested
  @DisplayName("Composition root 装配契约")
  class CompositionRootContract {

    @Test
    @DisplayName("所有 use case 正确装配")
    void allUseCasesAssembled() {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      assertThat(root.sessionList()).isNotNull();
      assertThat(root.projectList()).isNotNull();
      assertThat(root.dashboard()).isNotNull();
      assertThat(root.sessionDetail()).isNotNull();
      assertThat(root.diagnostics()).isNotNull();
    }

    @Test
    @DisplayName("无缓存 root 的 invalidateCache 为空操作")
    void noCacheRootInvalidationIsNoOp() {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      root.invalidateCache(); // 不应抛出
      assertThat(root.cache()).isNull();
    }
  }

  @Nested
  @DisplayName("缓存失效契约")
  class CacheInvalidationContract {

    @Test
    @DisplayName("scan 后缓存失效")
    void cacheInvalidatedAfterScan() throws Exception {
      QueryCache cache = new QueryCache(10);
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1), cache);

      // 首次查询，填充缓存
      root.sessionList().listWithAnomalies(SessionListFilter.defaults());
      assertThat(cache.size()).isEqualTo(1);

      // 模拟 scan 后失效
      root.invalidateCache();
      assertThat(cache.size()).isZero();
    }

    @Test
    @DisplayName("schema 版本变化导致缓存失效")
    void schemaVersionChangeInvalidatesCache() throws Exception {
      QueryCache cache = new QueryCache(10);
      QueryCompositionRoot root1 = new QueryCompositionRoot(ic, new SchemaVersion(1), cache);
      root1.dashboard().stats(AgentFilter.NONE);
      assertThat(cache.size()).isEqualTo(1);

      // 使用不同 schema 版本的 root 查询相同数据
      QueryCompositionRoot root2 = new QueryCompositionRoot(ic, new SchemaVersion(2), cache);
      root2.dashboard().stats(AgentFilter.NONE);
      // 两个不同 schema 版本各自缓存
      assertThat(cache.size()).isEqualTo(2);
    }
  }

  @Nested
  @DisplayName("端到端查询契约")
  class EndToEndQueryContract {

    @Test
    @DisplayName("session list 返回正确数量和异常摘要")
    void sessionListReturnsCorrectCount() throws Exception {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      var result = root.sessionList().listWithAnomalies(SessionListFilter.defaults());
      assertThat(result.page().size()).isEqualTo(1);
      assertThat(result.anomalies()).hasSize(1);
    }

    @Test
    @DisplayName("project list 返回正确项目数")
    void projectListReturnsCorrectCount() throws Exception {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      var result =
          root.projectList().list(com.feipi.session.browser.query.api.ProjectListFilter.defaults());
      assertThat(result.size()).isEqualTo(1);
    }

    @Test
    @DisplayName("dashboard stats 返回正确聚合")
    void dashboardStatsReturnsCorrectAggregate() throws Exception {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      var stats = root.dashboard().stats(AgentFilter.NONE);
      assertThat(stats.totalSessions()).isEqualTo(1);
    }

    @Test
    @DisplayName("session detail 无制品返回行级详情")
    void sessionDetailRowOnly() throws Exception {
      QueryCompositionRoot root = new QueryCompositionRoot(ic, new SchemaVersion(1));
      var detail =
          root.sessionDetail()
              .getDetail("cc:s1", com.feipi.session.browser.query.api.PayloadVisibility.STANDARD);
      assertThat(detail).isPresent();
      assertThat(detail.get().hasArtifact()).isFalse();
    }
  }
}
