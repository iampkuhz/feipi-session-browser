package com.feipi.session.browser.web.page;

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
 * <p>Acceptance contracts: UI-INTERACTION-008, UI-SD-019
 */
@DisplayName("SessionDetailPage 集成测试")
class SessionDetailPageTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

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
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("不存在的会话返回 404 和 Not Found 页面")
  void sessionNotFoundReturns404() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/nonexistent-id");
          assertThat(response.code()).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).containsIgnoringCase("Not Found");
        });
  }

  @Test
  @DisplayName("存在的会话返回 200 和 HTML")
  void existingSessionReturns200() throws Exception {
    insertTestSession();

    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          assertThat(response.code()).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).contains("Agent Run Profiler");
          assertThat(body).contains("data-trace-page");
        });
  }

  @Test
  @DisplayName("session detail 页面包含 payload 隐藏状态")
  void sessionDetailShowsPayloadHidden() throws Exception {
    insertTestSession();

    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          assertThat(response.code()).isEqualTo(200);
          String body = response.body().string();
          assertThat(body).contains("Payload hidden");
          assertThat(body).contains("sd-visibility-badge--hidden");
        });
  }

  @Test
  @DisplayName("session detail 页面包含 lazy-load JS")
  void sessionDetailIncludesLazyLoadJs() throws Exception {
    insertTestSession();

    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String body = response.body().string();
          assertThat(body).contains("session-detail/lazy_rounds.js");
          assertThat(body).contains("payload-api-base");
        });
  }

  @Test
  @DisplayName("session detail 页面包含 trace 面板")
  void sessionDetailIncludesTracePanel() throws Exception {
    insertTestSession();

    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test-session-1");
          String body = response.body().string();
          assertThat(body).contains("sd-trace-panel");
          assertThat(body).contains("data-trace-list");
          assertThat(body).contains("Trace");
        });
  }

  @Test
  @DisplayName("URL 编码的 agent 和 sessionId 正确解码")
  void urlEncodedParamsDecoded() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/sessions/claude_code/test%20session%20id");
          assertThat(response.code()).isEqualTo(404);
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
  }
}
