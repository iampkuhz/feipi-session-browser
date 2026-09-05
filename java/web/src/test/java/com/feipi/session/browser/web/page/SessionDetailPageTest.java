package com.feipi.session.browser.web.page;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import io.javalin.testtools.Response;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link SessionDetailPage} 集成测试。
 *
 * <p>验证 session detail 路由的 HTTP 行为：not found、正常渲染和模板上下文。
 *
 * <p>验收用例：UI-INTERACTION-008、UI-SD-019。
 */
@DisplayName("SessionDetailPage 集成测试")
class SessionDetailPageTest {

  private static final String APP_MARKER_HEADER = "X-Test-App-Marker";

  @TempDir Path tempDir;
  private IndexConnection indexConnection;
  private WebCompositionRoot activeWebRoot;
  private String appMarker;
  private boolean fixturePresent;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("session-detail-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
  }

  @AfterEach
  void tearDown() {
    // JavalinTest 在断言失败时不会停止服务；先停止服务，再释放数据库 fixture。
    try {
      if (activeWebRoot != null) {
        activeWebRoot.app().stop();
      }
    } finally {
      if (indexConnection != null) {
        indexConnection.close();
      }
    }
  }

  /** 标记当前测试的服务实例，区分路由错误与响应来自其他实例。 */
  private WebCompositionRoot createWebRoot(QueryCompositionRoot root) {
    activeWebRoot = new WebCompositionRoot(root, WebConfig.defaults());
    appMarker = UUID.randomUUID().toString();
    activeWebRoot.app().unsafe.routes.before(ctx -> ctx.header(APP_MARKER_HEADER, appMarker));
    return activeWebRoot;
  }

  /** 先验证实例身份，诊断仅包含状态码与固定布尔值，不输出正文或响应头值。 */
  private String assertCurrentAppResponse(Response response) {
    List<String> markers = response.headers().get(APP_MARKER_HEADER);
    boolean markerMatches = markers != null && markers.equals(List.of(appMarker));
    boolean cspPresent = response.headers().get("Content-Security-Policy") != null;
    boolean sessionNotFound = response.body().string().contains("会话不存在");
    String diagnostics =
        "HTTP %d; fixturePresent=%s, markerMatches=%s, CSPpresent=%s, sessionNotFound=%s"
            .formatted(response.code(), fixturePresent, markerMatches, cspPresent, sessionNotFound);
    assertThat(markerMatches).as(diagnostics).isTrue();
    return diagnostics;
  }

  @Test
  @DisplayName("不存在的会话返回 404 和 Not Found 页面")
  void sessionNotFoundReturns404() {
    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/nonexistent-id");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).containsIgnoringCase("Not Found");
        });
  }

  @Test
  @DisplayName("存在的会话返回 200 和 HTML")
  void existingSessionReturns200() throws Exception {
    insertTestSession();

    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).contains("Agent Run Profiler");
          assertThat(body).contains("data-trace-page");
          assertThat(body).contains("sd-kpi");
          assertThat(body).contains("Run Health");
        });
  }

  @Test
  @DisplayName("session detail summary strip 不展示 payload policy")
  void sessionDetailSummaryStripOmitsPayloadPolicy() throws Exception {
    insertTestSession();

    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).contains("data-summary-strip");
          assertThat(body).contains("data-session-updated");
          assertThat(body).doesNotContain("Payload hidden");
          assertThat(body).doesNotContain("data-session-payload-policy");
        });
  }

  @Test
  @DisplayName("session detail 页面不暴露 HTML 导出入口")
  void sessionDetailDoesNotExposeHtmlExportLink() throws Exception {
    insertTestSession();

    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).doesNotContain("Export session as HTML");
          assertThat(body).doesNotContain(">HTML</a>");
          assertThat(body).doesNotContain("/sessions/claude_code/test-session-1/export.html");
        });
  }

  @Test
  @DisplayName("session detail 页面包含 lazy-load JS")
  void sessionDetailIncludesLazyLoadJs() throws Exception {
    insertTestSession();

    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).contains("session-detail/lazy_rounds.js");
          assertThat(body).contains("payload-api-base");
        });
  }

  @Test
  @DisplayName("session detail 页面包含 trace 面板")
  void sessionDetailIncludesTracePanel() throws Exception {
    insertTestSession();

    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).contains("sd-trace-panel");
          assertThat(body).contains("data-trace-list");
          assertThat(body).contains("Trace");
        });
  }

  @Test
  @DisplayName("URL 编码的 agent 和 sessionId 正确解码")
  void urlEncodedParamsDecoded() {
    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = createWebRoot(root);

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test%20session%20id");
          String diagnostics = assertCurrentAppResponse(response);
          assertThat(response.code()).as(diagnostics).isEqualTo(404);
        });
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
    fixturePresent =
        new SqliteSessionQueryRepository(indexConnection)
            .getSession("claude_code:test-session-1")
            .isPresent();
    assertThat(fixturePresent).as("独立读连接必须可见已插入的 synthetic fixture").isTrue();
  }
}
