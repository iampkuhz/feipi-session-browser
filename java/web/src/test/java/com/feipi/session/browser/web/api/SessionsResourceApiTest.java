package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
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

/** Sessions resource APIs 的契约测试。 */
@DisplayName("Sessions resource APIs")
class SessionsResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("sessions-resource-api-test.db");
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
  @DisplayName("summary 返回 fixture 全量聚合和 token 四段")
  void summaryReturnsAllTotals() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertTotals(body, ApiContractFixture.ALL);
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("summary 按 failed 状态过滤并保持字段一致")
  void summaryFiltersFailedSessions() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/summary?status=failed");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertTotals(body, ApiContractFixture.FAILED);
          assertThat(body.at("/filters/status").asText()).isEqualTo("failed");
        });
  }

  @Test
  @DisplayName("rows 按 token total 排序并返回 pagination")
  void rowsSortByTokensDesc() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/rows?sort=tokens&dir=desc&page=1&page_size=25");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/pagination/totalItems").asLong()).isEqualTo(3);
          assertThat(body.at("/rows/0/sessionId").asText()).isEqualTo("s-alpha-001");
          assertThat(body.at("/rows/0/tokens/total").asLong()).isEqualTo(2000);
          assertThat(body.at("/rows/1/sessionId").asText()).isEqualTo("s-alpha-002");
          assertThat(body.at("/rows/1/tokens/total").asLong()).isEqualTo(1250);
          assertThat(body.at("/rows/2/sessionId").asText()).isEqualTo("s-beta-001");
          assertThat(body.at("/rows/2/tokens/total").asLong()).isEqualTo(800);
          assertTokenInvariant(body.at("/rows/0/tokens"));
        });
  }

  @Test
  @DisplayName("rows 搜索覆盖 project key")
  void rowsSearchMatchesProjectKey() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/rows?q=beta");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/pagination/totalItems").asLong()).isEqualTo(1);
          assertThat(body.at("/rows/0/sessionId").asText()).isEqualTo("s-beta-001");
          assertThat(body.at("/rows/0/projectKey").asText()).isEqualTo("/repo/beta");
          assertThat(textValues(body.at("/rows/0/matchReasons"))).contains("projectKey");
        });
  }

  @Test
  @DisplayName("rows 对非法 page_size 回退到 normalized 25")
  void rowsInvalidPageSizeFallsBackTo25() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/rows?page_size=13");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/pageSize").asInt()).isEqualTo(25);
          assertThat(body.at("/pagination/pageSize").asInt()).isEqualTo(25);
        });
  }

  @Test
  @DisplayName("options 返回固定 agent 和动态 model/project 候选")
  void optionsReturnFilterCandidates() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/options");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/agents/0/value").asText()).isEqualTo("all");
          assertThat(values(body.get("models"))).contains("claude-sonnet-4.5", "gpt-5.4");
          assertThat(values(body.get("projects"))).contains("/repo/alpha", "/repo/beta");
          assertThat(values(body.get("statuses"))).contains("failed", "no-failures");
        });
  }

  @Test
  @DisplayName("active-filters 返回 chip 和保留其它参数的 removeUrl")
  void activeFiltersReturnRemoveLinks() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response =
              client.get(
                  "/api/sessions/active-filters?agent=claude_code&status=failed&q=alpha&sort=tokens&dir=desc");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("chips")).hasSize(3);
          assertThat(body.at("/chips/0/key").asText()).isEqualTo("agent");
          assertThat(body.at("/chips/0/value").asText()).isEqualTo("Claude Code");
          assertThat(body.at("/chips/0/removeUrl").asText())
              .isEqualTo("/sessions?status=failed&q=alpha&sort=tokens&dir=desc");
          assertThat(body.at("/chips/1/key").asText()).isEqualTo("status");
          assertThat(body.at("/chips/2/key").asText()).isEqualTo("q");
          assertThat(body.at("/clearAllUrl").asText()).isEqualTo("/sessions");
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("API 未知路径仍返回 JSON error 而不是 HTML state")
  void unknownApiPathReturnsJsonError() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/no-such-resource");
          assertThat(response.code()).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).contains("not_found");
          assertThat(body).doesNotContain("state-panel");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static void assertTotals(JsonNode body, ApiContractFixture.ExpectedTotals expected) {
    assertThat(body.get("totalCount").asLong()).isEqualTo(expected.sessions());
    assertThat(body.get("projectCount").asLong()).isEqualTo(expected.projects());
    assertThat(body.get("failedTools").asLong()).isEqualTo(expected.failedTools());
    JsonNode tokens = body.get("tokens");
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

  private static java.util.List<String> values(JsonNode options) {
    java.util.List<String> result = new java.util.ArrayList<>();
    options.forEach(node -> result.add(node.get("value").asText()));
    return result;
  }

  private static java.util.List<String> textValues(JsonNode nodes) {
    java.util.List<String> result = new java.util.ArrayList<>();
    nodes.forEach(node -> result.add(node.asText()));
    return result;
  }
}
