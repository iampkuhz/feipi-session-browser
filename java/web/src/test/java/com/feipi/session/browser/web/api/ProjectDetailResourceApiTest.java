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
import org.assertj.core.data.Offset;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Project Detail resource APIs 的契约测试。 */
@DisplayName("Project Detail resource APIs")
class ProjectDetailResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Offset<Double> EPSILON = Offset.offset(0.0001);
  private static final String ALPHA = "%2Frepo%2Falpha";

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("project-detail-resource-api-test.db");
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
  @DisplayName("summary 返回单项目 KPI 和 token 四段")
  void summaryReturnsProjectScope() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/" + ALPHA + "/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/projectKey").asText()).isEqualTo("/repo/alpha");
          assertThat(body.get("projectName").asText()).isEqualTo("alpha");
          assertThat(body.get("totalSessions").asLong()).isEqualTo(2);
          assertThat(body.get("claudeSessions").asLong()).isEqualTo(2);
          assertThat(body.get("codexSessions").asLong()).isEqualTo(0);
          assertThat(body.get("failedTools").asLong()).isEqualTo(3);
          assertTokens(body.get("tokens"), ApiContractFixture.CLAUDE_CODE);
        });
  }

  @Test
  @DisplayName("不存在项目返回 JSON 404")
  void missingProjectReturnsJson404() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/%2Frepo%2Fmissing/summary");
          assertThat(response.code()).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).contains("not_found");
          assertThat(body).contains("project not found");
          assertThat(body).doesNotContain("state-panel");
        });
  }

  @Test
  @DisplayName("token-trend 的 rangeTotals 等于项目 token 总量")
  void tokenTrendReturnsProjectPoints() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/" + ALPHA + "/token-trend?grain=day");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertTokens(body.get("rangeTotals"), ApiContractFixture.CLAUDE_CODE);
          assertThat(body.get("points")).hasSize(2);
          assertThat(body.at("/points/0/label").asText()).isEqualTo("2026-06-01");
          assertThat(body.at("/points/0/tokens/total").asLong()).isEqualTo(2000);
          assertThat(body.at("/points/1/label").asText()).isEqualTo("2026-06-02");
          assertThat(sumNested(body.get("points"), "tokens", "total"))
              .isEqualTo(body.at("/rangeTotals/total").asLong());
        });
  }

  @Test
  @DisplayName("agent-mix 返回 share 且不越出项目 scope")
  void agentMixReturnsProjectScopedShares() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/" + ALPHA + "/agent-mix");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("totalSessions").asLong()).isEqualTo(2);
          JsonNode claude = findByAgent(body.get("rows"), "claude_code");
          assertThat(claude.get("sessions").asLong()).isEqualTo(2);
          assertThat(claude.at("/tokens/total").asLong()).isEqualTo(3250);
          assertThat(claude.get("failedTools").asLong()).isEqualTo(3);
          assertThat(claude.get("sessionShare").asDouble()).isCloseTo(100.0, EPSILON);
          assertThat(claude.get("sessionShareRatio").asDouble()).isCloseTo(1.0, EPSILON);
          assertThat(claude.get("tokenShareRatio").asDouble()).isCloseTo(1.0, EPSILON);
          JsonNode codex = findByAgent(body.get("rows"), "codex");
          assertThat(codex.get("sessions").asLong()).isEqualTo(0);
          assertThat(codex.at("/tokens/total").asLong()).isEqualTo(0);
          assertThat(sum(body.get("rows"), "sessionShareRatio")).isCloseTo(1.0, EPSILON);
          assertThat(sum(body.get("rows"), "tokenShareRatio")).isCloseTo(1.0, EPSILON);
        });
  }

  @Test
  @DisplayName("tool-hotspots 明确返回 unavailable reason")
  void toolHotspotsReturnUnavailableReason() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/" + ALPHA + "/tool-hotspots");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("available").asBoolean()).isFalse();
          assertThat(body.get("reason").asText()).isEqualTo("tool_name_breakdown_not_indexed");
          assertThat(body.get("rows")).isEmpty();
          assertThat(body.at("/state/kind").asText()).isEqualTo("no_results");
        });
  }

  @Test
  @DisplayName("sessions summary 固定 project scope 并支持 status 过滤")
  void sessionsSummaryIsProjectScoped() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/projects/" + ALPHA + "/sessions/summary?status=failed");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/project").asText()).isEqualTo("/repo/alpha");
          assertThat(body.at("/filters/status").asText()).isEqualTo("failed");
          assertThat(body.get("totalCount").asLong()).isEqualTo(2);
          assertThat(body.get("projectCount").asLong()).isEqualTo(1);
          assertTokens(body.get("tokens"), ApiContractFixture.CLAUDE_CODE);
        });
  }

  @Test
  @DisplayName("sessions rows 固定 project scope，排序不返回其他项目")
  void sessionsRowsAreProjectScoped() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response =
              client.get("/api/projects/" + ALPHA + "/sessions/rows?sort=tokens&dir=desc");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/pagination/totalItems").asLong()).isEqualTo(2);
          assertThat(body.at("/rows/0/projectKey").asText()).isEqualTo("/repo/alpha");
          assertThat(body.at("/rows/0/sessionId").asText()).isEqualTo("s-alpha-001");
          assertThat(body.at("/rows/1/projectKey").asText()).isEqualTo("/repo/alpha");
          assertThat(body.at("/rows/1/sessionId").asText()).isEqualTo("s-alpha-002");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static void assertTokens(JsonNode tokens, ApiContractFixture.ExpectedTotals expected) {
    assertThat(tokens.get("fresh").asLong()).isEqualTo(expected.fresh());
    assertThat(tokens.get("cacheRead").asLong()).isEqualTo(expected.cacheRead());
    assertThat(tokens.get("cacheWrite").asLong()).isEqualTo(expected.cacheWrite());
    assertThat(tokens.get("output").asLong()).isEqualTo(expected.output());
    assertThat(tokens.get("total").asLong()).isEqualTo(expected.total());
    assertThat(tokens.get("total").asLong())
        .isEqualTo(
            tokens.get("fresh").asLong()
                + tokens.get("cacheRead").asLong()
                + tokens.get("cacheWrite").asLong()
                + tokens.get("output").asLong());
  }

  private static long sumNested(JsonNode points, String objectField, String field) {
    long total = 0;
    for (JsonNode point : points) {
      total += point.get(objectField).get(field).asLong();
    }
    return total;
  }

  private static double sum(JsonNode rows, String field) {
    double total = 0.0;
    for (JsonNode row : rows) {
      total += row.get(field).asDouble();
    }
    return total;
  }

  private static JsonNode findByAgent(JsonNode rows, String agent) {
    for (JsonNode row : rows) {
      if (agent.equals(row.get("agent").asText())) {
        return row;
      }
    }
    throw new AssertionError("agent row not found: " + agent);
  }
}
