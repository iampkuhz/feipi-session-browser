package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
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

/** Projects resource APIs 的契约测试。 */
@DisplayName("Projects resource APIs")
class ProjectsResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("projects-resource-api-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    ApiContractFixture.insertThreeSessionFixture(indexConnection);
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("summary 返回项目/会话/token 聚合")
  void summaryReturnsProjectTotals() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("projectCount").asLong()).isEqualTo(2);
          assertThat(body.get("sessionCount").asLong()).isEqualTo(3);
          assertThat(body.get("toolCalls").asLong()).isEqualTo(7);
          assertThat(body.get("failedTools").asLong()).isEqualTo(3);
          assertTokens(body.get("tokens"), ApiContractFixture.ALL);
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("summary 搜索 beta 后只聚合匹配项目")
  void summarySearchMatchesProjectKey() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/summary?q=beta");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("projectCount").asLong()).isEqualTo(1);
          assertThat(body.get("sessionCount").asLong()).isEqualTo(1);
          assertThat(body.get("toolCalls").asLong()).isEqualTo(1);
          assertThat(body.get("failedTools").asLong()).isEqualTo(0);
          assertTokens(body.get("tokens"), ApiContractFixture.BETA);
          assertThat(body.at("/filters/q").asText()).isEqualTo("beta");
        });
  }

  @Test
  @DisplayName("rows 按 token 排序并保持 summary/rows 一致")
  void rowsSortByTokensDesc() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/rows?sort=tokens&dir=desc&page=1&page_size=25");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/pagination/totalItems").asLong()).isEqualTo(2);
          JsonNode first = body.at("/rows/0");
          assertThat(first.get("projectKey").asText()).isEqualTo("/repo/alpha");
          assertThat(first.get("totalSessions").asLong()).isEqualTo(2);
          assertThat(first.get("claudeSessions").asLong()).isEqualTo(2);
          assertThat(first.get("codexSessions").asLong()).isEqualTo(0);
          assertThat(first.at("/tokens/total").asLong()).isEqualTo(3250);
          assertTokenInvariant(first.get("tokens"));
          JsonNode second = body.at("/rows/1");
          assertThat(second.get("projectKey").asText()).isEqualTo("/repo/beta");
          assertThat(second.at("/tokens/total").asLong()).isEqualTo(800);
        });
  }

  @Test
  @DisplayName("rows 搜索 alpha 返回单项目且分页 totalItems 一致")
  void rowsSearchReturnsSingleProject() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/rows?q=alpha");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/pagination/totalItems").asLong()).isEqualTo(1);
          assertThat(body.at("/rows/0/projectKey").asText()).isEqualTo("/repo/alpha");
          assertThat(body.at("/rows/0/failedTools").asLong()).isEqualTo(3);
          assertThat(body.at("/rows/0/detailUrl").asText()).isEqualTo("/projects/%2Frepo%2Falpha");
          assertThat(body.at("/filters/q").asText()).isEqualTo("alpha");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static void assertTokens(JsonNode tokens, ApiContractFixture.ExpectedTotals expected) {
    assertThat(tokens.get("fresh").asLong()).isEqualTo(expected.fresh());
    assertThat(tokens.get("cacheRead").asLong()).isEqualTo(expected.cacheRead());
    assertThat(tokens.get("cacheWrite").asLong()).isEqualTo(expected.cacheWrite());
    assertThat(tokens.get("output").asLong()).isEqualTo(expected.output());
    assertThat(tokens.get("total").asLong()).isEqualTo(expected.total());
    assertTokenInvariant(tokens);
  }

  private static void assertTokenInvariant(JsonNode tokens) {
    long sum =
        tokens.get("fresh").asLong()
            + tokens.get("cacheRead").asLong()
            + tokens.get("cacheWrite").asLong()
            + tokens.get("output").asLong();
    assertThat(tokens.get("total").asLong()).isEqualTo(sum);
  }
}
