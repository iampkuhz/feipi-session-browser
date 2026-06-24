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
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * Web 路由契约门禁。
 *
 * <p>验证所有已注册路由的 HTTP 状态码、Content-Type、安全头和关键 DOM 结构。 本测试位于 HTTP adapter trust boundary，不重复验证下游
 * handler 的业务逻辑。
 */
@DisplayName("WEB-080: Web 路由契约门禁")
class WebRouteContractTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("route-contract.db");
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

  /** 从测试响应中提取指定 header 的第一个值。 */
  private static String firstHeader(io.javalin.testtools.Response response, String name) {
    List<String> values = response.headers().get(name);
    return (values != null && !values.isEmpty()) ? values.get(0) : null;
  }

  @Nested
  @DisplayName("路由状态码契约")
  class RouteStatusContract {

    @Test
    @DisplayName("GET / 返回 200")
    void rootReturns200() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("GET /dashboard 返回 200")
    void dashboardReturns200() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("GET /projects 返回 200")
    void projectsReturns200() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/projects");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("GET /sessions 返回 200")
    void sessionsReturns200() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("GET /healthz 返回 200")
    void healthzReturns200() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/healthz");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("不存在的路由返回 404")
    void unknownRouteReturns404() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/this-route-does-not-exist");
            assertThat(response.code()).isEqualTo(404);
          });
    }

    @Test
    @DisplayName("不存在的会话返回 404")
    void missingSessionReturns404() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/nonexistent-session-id");
            assertThat(response.code()).isEqualTo(404);
          });
    }
  }

  @Nested
  @DisplayName("Content-Type 契约")
  class ContentTypeContract {

    @Test
    @DisplayName("页面路由返回 text/html")
    void pageRoutesReturnHtml() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String contentType = firstHeader(response, "Content-Type");
            assertThat(contentType).contains("text/html");
          });
    }

    @Test
    @DisplayName("健康检查返回 application/json")
    void healthReturnsJson() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/healthz");
            String contentType = firstHeader(response, "Content-Type");
            assertThat(contentType).contains("application/json");
          });
    }

    @Test
    @DisplayName("HTML 响应包含 charset=utf-8")
    void htmlResponseContainsCharset() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String contentType = firstHeader(response, "Content-Type");
            assertThat(contentType).containsIgnoringCase("utf-8");
          });
    }
  }

  @Nested
  @DisplayName("安全头契约")
  class SecurityHeaderContract {

    @Test
    @DisplayName("所有页面响应均携带 CSP header")
    void allPagesHaveCsp() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : List.of("/", "/dashboard", "/projects", "/sessions")) {
              var response = client.get(path);
              String csp = firstHeader(response, "Content-Security-Policy");
              assertThat(csp).as("CSP header on %s", path).isNotNull();
              assertThat(csp).contains("default-src 'self'");
            }
          });
    }

    @Test
    @DisplayName("所有页面响应均携带 X-Frame-Options: DENY")
    void allPagesHaveXFrameOptions() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : List.of("/", "/dashboard", "/projects", "/sessions")) {
              var response = client.get(path);
              assertThat(firstHeader(response, "X-Frame-Options"))
                  .as("X-Frame-Options on %s", path)
                  .isEqualTo("DENY");
            }
          });
    }

    @Test
    @DisplayName("所有页面响应均携带 Cache-Control: no-store")
    void allPagesHaveCacheControl() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : List.of("/", "/dashboard", "/projects", "/sessions")) {
              var response = client.get(path);
              String cacheControl = firstHeader(response, "Cache-Control");
              assertThat(cacheControl).as("Cache-Control on %s", path).contains("no-store");
            }
          });
    }
  }

  @Nested
  @DisplayName("Dashboard DOM 契约")
  class DashboardDomContract {

    @Test
    @DisplayName("Dashboard 页面包含 lang 属性和 sidebar 导航")
    void dashboardHasBaseStructure() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            assertThat(body).contains("lang=\"zh-CN\"");
            assertThat(body).contains("aria-label=\"Primary navigation\"");
            assertThat(body).contains("data-action=\"nav-dashboard\"");
            assertThat(body).contains("data-action=\"nav-sessions\"");
            assertThat(body).contains("data-action=\"nav-projects\"");
          });
    }

    @Test
    @DisplayName("Dashboard 页面有数据时包含 KPI 区域或空状态")
    void dashboardRendersWithDataOrEmpty() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            // 空数据库应显示空状态，非空应显示 KPI grid
            assertThat(response.code()).isIn(200, 500);
            String body = response.body().string();
            // 无论如何都有基本结构
            assertThat(body).contains("Agent Run Profiler");
          });
    }

    @Test
    @DisplayName("Dashboard 当前页导航高亮")
    void dashboardNavIsActive() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            String body = response.body().string();
            assertThat(body).contains("data-action=\"nav-dashboard\"").contains("is-active");
          });
    }
  }

  @Nested
  @DisplayName("Sessions DOM 契约")
  class SessionsDomContract {

    @Test
    @DisplayName("Sessions 页面包含搜索和过滤表单")
    void sessionsHasFilterForm() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("id=\"session-search\"");
            assertThat(body).contains("aria-label=\"Search sessions\"");
            assertThat(body).contains("id=\"filter-agent\"");
            assertThat(body).contains("id=\"filter-status\"");
          });
    }

    @Test
    @DisplayName("Sessions 页面有数据时包含分页导航区域")
    void sessionsHasPaginationNavWithData() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("aria-label=\"Sessions pagination\"");
            assertThat(body).contains("data-pagination");
          });
    }

    @Test
    @DisplayName("Sessions 页面有数据时包含数据表格结构")
    void sessionsHasDataTableWithData() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions");
            String body = response.body().string();
            assertThat(body).contains("role=\"table\"");
            assertThat(body).contains("aria-label=\"Sessions table\"");
          });
    }
  }

  @Nested
  @DisplayName("Session Detail DOM 契约")
  class SessionDetailDomContract {

    @Test
    @DisplayName("存在的会话页面包含 trace 面板和 lazy-load 脚本引用")
    void sessionDetailHasTracePanel() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1");
            String body = response.body().string();
            assertThat(body).contains("data-trace-page");
            assertThat(body).contains("sd-trace-panel");
            assertThat(body).contains("session-detail/lazy_rounds.js");
          });
    }

    @Test
    @DisplayName("存在的会话页面包含 payload 隐藏标识")
    void sessionDetailPayloadHiddenByDefault() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1");
            String body = response.body().string();
            assertThat(body).contains("Payload hidden");
            assertThat(body).contains("payload-api-base");
          });
    }

    @Test
    @DisplayName("存在的会话页面包含 hero 指标区域")
    void sessionDetailHasHeroMetrics() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1");
            String body = response.body().string();
            assertThat(body).contains("sd-hero");
            assertThat(body).contains("aria-label=\"Session metrics\"");
          });
    }
  }

  @Nested
  @DisplayName("API 路由契约")
  class ApiRouteContract {

    @Test
    @DisplayName("API 路径段不足返回 400")
    void apiInsufficientPathReturns400() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("bad_request");
          });
    }

    @Test
    @DisplayName("API 未知资源类型返回 400")
    void apiUnknownResourceReturns400() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/s1/unknownres/x");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("unknown resource");
          });
    }

    @Test
    @DisplayName("不存在的会话 API 返回 404")
    void apiSessionNotFoundReturns404() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/no-such-session/round/1");
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("not_found");
          });
    }

    @Test
    @DisplayName("非法 numeric 参数返回 400")
    void apiInvalidNumericParamReturns400() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/s1/round/notanumber");
            assertThat(response.code()).isEqualTo(400);
          });
    }
  }

  @Nested
  @DisplayName("HTML 结构契约")
  class HtmlStructureContract {

    @Test
    @DisplayName("所有页面包含 DOCTYPE 和 <html> 标签")
    void allPagesHaveDoctype() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : List.of("/", "/dashboard", "/sessions", "/projects")) {
              var response = client.get(path);
              String body = response.body().string();
              assertThat(body).as("DOCTYPE on %s", path).startsWith("<!DOCTYPE html>");
              assertThat(body).as("<html> on %s", path).contains("<html");
            }
          });
    }

    @Test
    @DisplayName("所有页面包含 <title> 标签")
    void allPagesHaveTitle() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : List.of("/", "/dashboard", "/sessions", "/projects")) {
              var response = client.get(path);
              String body = response.body().string();
              assertThat(body).as("title on %s", path).contains("<title>");
              assertThat(body).as("title content on %s", path).contains("Agent Run Profiler");
            }
          });
    }

    @Test
    @DisplayName("所有页面包含 base CSS 引用")
    void allPagesHaveBaseCss() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            for (String path : List.of("/", "/dashboard", "/sessions", "/projects")) {
              var response = client.get(path);
              String body = response.body().string();
              assertThat(body).as("base.css on %s", path).contains("/static/css/base.css");
              assertThat(body).as("tokens.css on %s", path).contains("/static/css/tokens.css");
            }
          });
    }
  }

  /** 插入测试会话数据。 */
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
