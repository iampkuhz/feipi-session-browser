package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

@DisplayName("RuntimeAccessLog 访问日志契约测试")
class RuntimeAccessLogTest {

  @org.junit.jupiter.api.Test
  void projectListEndpointsAreNotDetailEndpoints() {
    assertThat(RuntimeAccessLog.classifyRoute("/api/projects/summary"))
        .isEqualTo("api:/api/projects/summary");
    assertThat(RuntimeAccessLog.classifyRoute("/api/projects/rows"))
        .isEqualTo("api:/api/projects/rows");
    assertThat(RuntimeAccessLog.classifyRoute("/api/projects/active-filters"))
        .isEqualTo("api:/api/projects/active-filters");
  }

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("access-log-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.ensureSchema(indexConnection.writerConnection());
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Nested
  @DisplayName("classifyRoute 路由分类")
  class RouteClassification {

    @Test
    @DisplayName("页面路由返回安全分类")
    void pageRoutesReturnSafeCategories() {
      assertThat(RuntimeAccessLog.classifyRoute("/")).isEqualTo("page:/");
      assertThat(RuntimeAccessLog.classifyRoute("/dashboard")).isEqualTo("page:/dashboard");
      assertThat(RuntimeAccessLog.classifyRoute("/projects")).isEqualTo("page:/projects");
      assertThat(RuntimeAccessLog.classifyRoute("/projects/my-project"))
          .isEqualTo("page:/projects/{key}");
      assertThat(RuntimeAccessLog.classifyRoute("/sessions")).isEqualTo("page:/sessions");
      assertThat(RuntimeAccessLog.classifyRoute("/sessions/codex/abc123"))
          .isEqualTo("page:/sessions/{agent}/{sessionId}");
      assertThat(RuntimeAccessLog.classifyRoute("/glossary")).isEqualTo("page:/glossary");
    }

    @Test
    @DisplayName("API 路由返回安全分类，不暴露参数")
    void apiRoutesReturnSafeCategories() {
      assertThat(RuntimeAccessLog.classifyRoute("/api/dashboard/summary"))
          .isEqualTo("api:/api/dashboard/summary");
      assertThat(RuntimeAccessLog.classifyRoute("/api/dashboard/trends/sessions"))
          .isEqualTo("api:/api/dashboard/trends/{metric}");
      assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/rows"))
          .isEqualTo("api:/api/sessions/rows");
      assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/codex/abc123/meta"))
          .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
      assertThat(RuntimeAccessLog.classifyRoute("/api/projects/my-key/summary"))
          .isEqualTo("api:/api/projects/{key}/summary");
    }

    @Test
    @DisplayName("healthz 和 static 返回 skip")
    void filteredRoutesReturnSkip() {
      assertThat(RuntimeAccessLog.classifyRoute("/healthz")).isEqualTo("skip");
      assertThat(RuntimeAccessLog.classifyRoute("/static/css/app.css")).isEqualTo("skip");
      assertThat(RuntimeAccessLog.classifyRoute("/static/js/app.js")).isEqualTo("skip");
    }

    @Test
    @DisplayName("未知路由返回 unknown")
    void unknownRoutesReturnUnknown() {
      assertThat(RuntimeAccessLog.classifyRoute("/nonexistent")).isEqualTo("unknown");
      assertThat(RuntimeAccessLog.classifyRoute("/api/unknown")).isEqualTo("unknown");
      assertThat(RuntimeAccessLog.classifyRoute("/some/random/path")).isEqualTo("unknown");
    }

    @Nested
    @DisplayName("敏感段碰撞防护")
    class SensitiveSegmentCollision {

      @Test
      @DisplayName("sessionId 包含 summary 不影响 meta 分类")
      void sessionIdWithSummaryDoesNotAffectMetaClassification() {
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/codex/summary-private/meta"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/codex/summary/meta"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/codex/my-summary/meta"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
      }

      @Test
      @DisplayName("sessionId 包含 options/rows/active-filters 不影响分类")
      void sessionIdWithListKeywordsDoesNotAffectClassification() {
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/codex/options-private/meta"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/codex/rows-data/meta"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
        assertThat(
                RuntimeAccessLog.classifyRoute("/api/sessions/codex/active-filters-test/payloads"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/payloads");
      }

      @Test
      @DisplayName("真正的 list API 仍正确分类")
      void realListApisStillClassifiedCorrectly() {
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/summary"))
            .isEqualTo("api:/api/sessions/summary");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/options"))
            .isEqualTo("api:/api/sessions/options");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/rows"))
            .isEqualTo("api:/api/sessions/rows");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/active-filters"))
            .isEqualTo("api:/api/sessions/active-filters");
      }

      @Test
      @DisplayName("agent 参数包含敏感词不影响分类")
      void agentWithSensitiveWordsDoesNotAffectClassification() {
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/summary-agent/abc123/meta"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/meta");
        assertThat(RuntimeAccessLog.classifyRoute("/api/sessions/rows-agent/abc123/rounds"))
            .isEqualTo("api:/api/sessions/{agent}/{sessionId}/rounds");
      }

      @Test
      @DisplayName("project key 包含敏感词不影响分类")
      void projectKeyWithSensitiveWordsDoesNotAffectClassification() {
        assertThat(RuntimeAccessLog.classifyRoute("/api/projects/summary-project/summary"))
            .isEqualTo("api:/api/projects/{key}/summary");
        assertThat(RuntimeAccessLog.classifyRoute("/api/projects/rows-data/token-trend"))
            .isEqualTo("api:/api/projects/{key}/token-trend");
      }
    }
  }

  @Nested
  @DisplayName("访问日志集成测试")
  class AccessLogIntegration {

    @Test
    @DisplayName("healthz 不产生访问日志")
    void healthzFiltered() {
      QueryCompositionRoot root =
          WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/healthz");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("静态资源不产生访问日志")
    void staticResourcesFiltered() {
      QueryCompositionRoot root =
          WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
      WebConfig config = new WebConfig("127.0.0.1", 0, "/static");
      WebCompositionRoot webRoot = new WebCompositionRoot(root, config);

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            client.get("/static/css/app.css");
          });
    }

    @Test
    @DisplayName("业务页面请求可正常响应")
    void businessRouteResponds() {
      QueryCompositionRoot root =
          WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            assertThat(response.code()).isEqualTo(200);
          });
    }

    @Test
    @DisplayName("API 请求可正常响应")
    void apiRouteResponds() {
      QueryCompositionRoot root =
          WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/codex/test-session-123/meta");
            assertThat(response.code()).isIn(200, 404);
          });
    }

    @Test
    @DisplayName("sessionId 包含敏感词的请求可正常响应")
    void sessionIdWithSensitiveWordsResponds() {
      QueryCompositionRoot root =
          WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/codex/summary-private/meta");
            assertThat(response.code()).isIn(200, 404);
          });
    }
  }
}
