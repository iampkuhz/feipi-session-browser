package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
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
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    assertThatThrownBy(() -> new WebCompositionRoot(root, null))
        .isInstanceOf(NullPointerException.class)
        .hasMessageContaining("config");
  }

  @Test
  @DisplayName("createServer 返回可用的 WebServer")
  void createServerReturnsUsableServer() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());
    WebServer server = webRoot.createServer();

    assertThat(server).isNotNull();
    assertThat(server.isRunning()).isFalse();
  }

  @Test
  @DisplayName("健康检查路由通过 composition root 可达")
  void healthRouteReachableThroughRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
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
  @DisplayName("未知路由返回 404 和 JSON 错误")
  void unknownRouteReturns404() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/nonexistent");
          assertThat(response.code()).isEqualTo(404);
          assertThat(response.body().string()).contains("not_found");
        });
  }

  @Test
  @DisplayName("queryRoot 返回构造时传入的实例")
  void queryRootReturnsSameInstance() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    assertThat(webRoot.queryRoot()).isSameAs(root);
  }

  @Test
  @DisplayName("app 返回非 null 的 Javalin 实例")
  void appReturnsNonNull() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    assertThat(webRoot.app()).isNotNull();
  }
}
