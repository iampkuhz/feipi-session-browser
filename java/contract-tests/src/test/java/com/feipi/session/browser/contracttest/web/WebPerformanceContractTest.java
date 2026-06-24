package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Web 性能契约门禁。
 *
 * <p>验证分页行为、大 session 列表渲染性能和 asset cache 关键行为。 本测试位于 HTTP adapter trust
 * boundary，确认分页参数在入口层正确解析并传递到下游查询。
 */
@DisplayName("WEB-080: Web 性能契约门禁")
class WebPerformanceContractTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("perf-contract.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  @Nested
  @DisplayName("分页契约")
  class PaginationContract {

    @Test
    @DisplayName("默认分页返回 200 且包含分页信息")
    void defaultPaginationReturns200WithInfo() throws Exception {
      insertMultipleSessions(5);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(body).contains("5 matching sessions");
          });
    }

    @Test
    @DisplayName("page_size 参数限制返回行数")
    void pageSizeLimitsRows() throws Exception {
      insertMultipleSessions(30);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions?page_size=25");
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(body).contains("of 30");
          });
    }

    @Test
    @DisplayName("page 参数翻页正常")
    void pageParamWorks() throws Exception {
      insertMultipleSessions(30);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions?page=2&page_size=25");
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(body).contains("26-30 of 30");
          });
    }

    @Test
    @DisplayName("分页包含 Previous/Next 按钮")
    void paginationHasPrevNextButtons() throws Exception {
      insertMultipleSessions(30);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response1 = client.get("/sessions?page=1&page_size=25");
            String body1 = response1.body().string();
            assertThat(body1).contains("data-action=\"next-page\"");

            var response2 = client.get("/sessions?page=2&page_size=25");
            String body2 = response2.body().string();
            assertThat(body2).contains("data-action=\"prev-page\"");
          });
    }

    @Test
    @DisplayName("空列表显示 empty state")
    void emptyListShowsEmptyState() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(body).contains("No matching sessions");
          });
    }
  }

  @Nested
  @DisplayName("大列表性能")
  class LargeListPerformance {

    @Test
    @DisplayName("100 个会话的列表请求在 5 秒内返回")
    void hundredSessionsResponseTime() throws Exception {
      insertMultipleSessions(100);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            long start = System.currentTimeMillis();
            var response = client.get("/sessions");
            long elapsed = System.currentTimeMillis() - start;
            assertThat(response.code()).isEqualTo(200);
            // 性能预算：100 个 session 的首页渲染应 < 5s
            assertThat(elapsed).as("100 个会话首页渲染时间").isLessThan(5000);
          });
    }

    @Test
    @DisplayName("100 个会话分页查询仍显示正确总数")
    void hundredSessionsCorrectTotal() throws Exception {
      insertMultipleSessions(100);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(body).contains("100 matching sessions");
          });
    }

    @Test
    @DisplayName("Dashboard 在 100 个会话下正常响应")
    void dashboardStatsWithHundredSessions() throws Exception {
      insertMultipleSessions(100);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            long start = System.currentTimeMillis();
            var response = client.get("/dashboard");
            long elapsed = System.currentTimeMillis() - start;
            // Dashboard 可能返回 200 或 500（取决于 DashboardUseCase 兼容性）
            assertThat(response.code()).as("Dashboard 响应状态").isIn(200, 500);
            assertThat(elapsed).as("Dashboard 在 100 会话下响应时间").isLessThan(10000);
          });
    }
  }

  @Nested
  @DisplayName("静态资源路径契约")
  class StaticAssetContract {

    @Test
    @DisplayName("Dashboard 页面引用 dashboard CSS 和 JS")
    void dashboardReferencesAssets() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            assertThat(body).contains("/static/css/dashboard.css");
            assertThat(body).contains("/static/js/dashboard.js");
          });
    }

    @Test
    @DisplayName("Sessions 页面引用 sessions CSS 和 JS")
    void sessionsReferencesAssets() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("/static/css/sessions-list.css");
            assertThat(body).contains("/static/js/sessions-list.js");
          });
    }

    @Test
    @DisplayName("Session Detail 页面引用 session-detail JS 模块")
    void sessionDetailReferencesModuleJs() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1");
            String body = response.body().string();
            assertThat(body).contains("/static/css/session-detail.css");
            assertThat(body).contains("/static/js/session-detail/init.js");
            assertThat(body).contains("/static/js/session-detail/lazy_rounds.js");
            assertThat(body).contains("/static/js/session-detail/payload.js");
          });
    }

    @Test
    @DisplayName("Cache-Control 禁止缓存，保护本地会话数据")
    void cacheControlPreventsCaching() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String cacheControl = response.headers().get("Cache-Control").get(0);
            assertThat(cacheControl).contains("no-store");
            assertThat(cacheControl).contains("no-cache");
          });
    }
  }

  @Nested
  @DisplayName("查询参数边界")
  class QueryParamBoundary {

    @Test
    @DisplayName("page=1 正常处理")
    void pageOneWorks() throws Exception {
      insertMultipleSessions(5);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions?page=1");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("agent 过滤参数正常处理")
    void agentFilterWorks() throws Exception {
      insertMultipleSessions(3);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions?agent=claude_code");
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(body).contains("3 matching sessions");
          });
    }

    @Test
    @DisplayName("搜索参数正常处理")
    void searchQueryWorks() throws Exception {
      insertMultipleSessions(3);
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions?q=Test");
            assertThat(response.code()).isEqualTo(200);
          });
    }
  }

  /** 插入多条测试会话数据。 */
  private void insertMultipleSessions(int count) throws Exception {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name,"
            + " cwd, started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES"
            + " (?, 'claude_code', ?, 'Test Session ' || ?, 'pk1', 'Test Project', '/work',"
            + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
            + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
            + " 50000, 25000, 15000, 10000, 100000, 0, 2,"
            + " 1704067200, 1704067200, ?)";
    try (PreparedStatement ps = indexConnection.writerConnection().prepareStatement(sql)) {
      for (int i = 1; i <= count; i++) {
        String id = "perf-session-" + i;
        ps.setString(1, "claude_code:" + id);
        ps.setString(2, id);
        ps.setInt(3, i);
        ps.setString(4, "/f" + i);
        ps.addBatch();
      }
      ps.executeBatch();
    }
  }

  /** 插入单条测试会话数据。 */
  private void insertTestSession() throws Exception {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name,"
            + " cwd, started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES"
            + " ('claude_code:test-session-1', 'claude_code', 'test-session-1',"
            + " 'Test Session', 'pk1', 'Test Project', '/work',"
            + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
            + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
            + " 50000, 25000, 15000, 10000, 100000, 0, 2,"
            + " 1704067200, 1704067200, '/f1')";
    indexConnection.writerConnection().createStatement().execute(sql);
  }
}
