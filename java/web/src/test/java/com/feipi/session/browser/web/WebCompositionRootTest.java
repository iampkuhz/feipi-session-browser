package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
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
 * {@link WebCompositionRoot} 集成测试。
 *
 * <p>使用内存 SQLite 验证 composition root 的装配和健康检查路由。
 */
@DisplayName("WebCompositionRoot 集成测试")
class WebCompositionRootTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("web-root-test.db");
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
  @DisplayName("构造器不得接受 null queryRoot")
  void nullQueryRootThrows() {
    assertThatThrownBy(() -> new WebCompositionRoot(null, WebConfig.defaults()))
        .isInstanceOf(NullPointerException.class)
        .hasMessageContaining("queryRoot");
  }

  @Test
  @DisplayName("构造器不得接受 null config")
  void nullConfigThrows() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    assertThatThrownBy(() -> new WebCompositionRoot(root, null))
        .isInstanceOf(NullPointerException.class)
        .hasMessageContaining("config");
  }

  @Test
  @DisplayName("createServer 返回可用的 WebServer")
  void createServerReturnsUsableServer() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());
    WebServer server = webRoot.createServer();

    assertThat(server).isNotNull();
    assertThat(server.isRunning()).isFalse();
  }

  @Test
  @DisplayName("健康检查路由通过 composition root 可达")
  void healthRouteReachableThroughRoot() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/healthz");
          assertThat(response.code()).isEqualTo(200);
          assertThat(response.body().string()).contains("ok");
        });
  }

  @Test
  @DisplayName("未知页面路由返回 404 和 HTML 状态页")
  void unknownRouteReturns404() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/nonexistent");
          assertThat(response.code()).isEqualTo(404);
          assertThat(response.body().string()).contains("Page Not Found");
        });
  }

  @Test
  @DisplayName("项目详情路由接受 raw slash path 和 encoded path")
  void projectDetailRouteAcceptsRawAndEncodedAbsolutePath() throws Exception {
    String projectKey = "/Users/zhehan/Documents/tools/llm/feipi-session-browser-java";
    indexConnection
        .writerConnection()
        .createStatement()
        .executeUpdate(
            "INSERT INTO sessions"
                + " (session_key, agent, session_id, title, project_key, project_name, cwd,"
                + " started_at, ended_at, duration_seconds, model_execution_seconds,"
                + " tool_execution_seconds, model, git_branch, source,"
                + " user_message_count, assistant_message_count, tool_call_count,"
                + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
                + " total_tokens, failed_tool_count, subagent_instance_count,"
                + " indexed_at, file_mtime, file_path)"
                + " VALUES ('codex:raw-route', 'codex', 'raw-route', 'Raw route session',"
                + " '/Users/zhehan/Documents/tools/llm/feipi-session-browser-java',"
                + " 'feipi-session-browser-java',"
                + " '/Users/zhehan/Documents/tools/llm/feipi-session-browser-java',"
                + " '2026-07-04T10:00:00Z', '2026-07-04T10:01:00Z',"
                + " 60.0, 45.0, 5.0, 'gpt-5', 'main', 'fixture',"
                + " 1, 1, 0, 10, 20, 30, 40, 100, 0, 0,"
                + " '2026-07-04T10:02:00Z', 1, '/tmp/raw-route.json')");

    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          for (String path :
              new String[] {
                "/projects/%2FUsers%2Fzhehan%2FDocuments%2Ftools%2Fllm%2Ffeipi-session-browser-java",
                "/projects//Users/zhehan/Documents/tools/llm/feipi-session-browser-java"
              }) {
            var response = client.get(path);
            assertThat(response.code()).isEqualTo(200);
            assertThat(response.body().string()).contains("<h1>feipi-session-browser-java</h1>");
          }
        });
  }

  @Test
  @DisplayName("queryRoot 返回构造时传入的实例")
  void queryRootReturnsSameInstance() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    assertThat(webRoot.queryRoot()).isSameAs(root);
  }

  @Test
  @DisplayName("app 返回非 null 的 Javalin 实例")
  void appReturnsNonNull() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    assertThat(webRoot.app()).isNotNull();
  }
}
