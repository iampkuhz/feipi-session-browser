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
import org.assertj.core.data.Offset;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Dashboard resource APIs 的契约测试。 */
@DisplayName("Dashboard resource APIs")
class DashboardResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Offset<Double> EPSILON = Offset.offset(0.0001);

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("dashboard-resource-api-test.db");
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
  @DisplayName("summary 返回 KPI 原始值和 token 四段")
  void summaryReturnsRawKpis() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("sessionCount").asLong()).isEqualTo(3);
          assertThat(body.get("projectCount").asLong()).isEqualTo(2);
          assertThat(body.at("/agents/claudeCode").asLong()).isEqualTo(2);
          assertThat(body.at("/agents/codex").asLong()).isEqualTo(1);
          assertThat(body.at("/agents/qoder").asLong()).isEqualTo(0);
          assertThat(body.get("toolCalls").asLong()).isEqualTo(7);
          assertThat(body.get("failedTools").asLong()).isEqualTo(3);
          assertThat(body.get("userMessages").asLong()).isEqualTo(4);
          assertTokens(body.get("tokens"), ApiContractFixture.ALL);
          assertThat(body.at("/cacheReadRatio/value").asDouble())
              .isCloseTo(900.0 / 3100.0, EPSILON);
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("summary 支持单 agent scope")
  void summarySupportsAgentScope() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/summary?agent=claude-code");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/agent").asText()).isEqualTo("claude-code");
          assertThat(body.get("sessionCount").asLong()).isEqualTo(2);
          assertThat(body.get("projectCount").asLong()).isEqualTo(1);
          assertTokens(body.get("tokens"), ApiContractFixture.CLAUDE_CODE);
        });
  }

  @Test
  @DisplayName("sessions trend 的 rangeTotal 等于 points 求和")
  void sessionsTrendHasRangeInvariant() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/trends/sessions?grain=week");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("rangeTotal").asLong()).isEqualTo(3);
          assertThat(body.get("points")).hasSize(2);
          assertThat(body.at("/points/0/date").asText()).isEqualTo("2026-06-01");
          assertThat(body.at("/points/0/totalCount").asLong()).isEqualTo(2);
          assertThat(body.at("/points/1/date").asText()).isEqualTo("2026-06-02");
          assertThat(sum(body.get("points"), "totalCount"))
              .isEqualTo(body.get("rangeTotal").asLong());
        });
  }

  @Test
  @DisplayName("token trend 的 rangeTotals 等于 points token 求和")
  void tokenTrendHasSegmentInvariant() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/trends/tokens?grain=week");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertTokens(body.get("rangeTotals"), ApiContractFixture.ALL);
          assertThat(sumNested(body.get("points"), "tokens", "total"))
              .isEqualTo(body.at("/rangeTotals/total").asLong());
          assertThat(body.at("/points/0/tokens/total").asLong()).isEqualTo(2800);
          assertThat(body.at("/points/1/tokens/total").asLong()).isEqualTo(1250);
        });
  }

  @Test
  @DisplayName("prompts trend 返回 prompts/assistant/tool 原始计数")
  void promptTrendReturnsRawCounts() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/trends/prompts?grain=week");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("rangeTotalPrompts").asLong()).isEqualTo(4);
          assertThat(body.at("/points/0/totalPrompts").asLong()).isEqualTo(3);
          assertThat(body.at("/points/0/toolCalls").asLong()).isEqualTo(5);
          assertThat(sum(body.get("points"), "totalPrompts"))
              .isEqualTo(body.get("rangeTotalPrompts").asLong());
        });
  }

  @Test
  @DisplayName("cache-health 返回可计算 ratio 且不伪造 0")
  void cacheHealthReturnsRatios() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/trends/cache-health?grain=week");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/latestRatio/value").asDouble()).isCloseTo(0.5, EPSILON);
          assertThat(body.at("/lowestRatio/value").asDouble()).isCloseTo(400.0 / 2100.0, EPSILON);
          assertThat(body.at("/points/0/average/totalInput").asLong()).isEqualTo(2100);
          assertThat(body.at("/points/0/average/ratio/value").asDouble())
              .isCloseTo(400.0 / 2100.0, EPSILON);
          assertThat(body.at("/points/0/qoder/ratio/value").isNull()).isTrue();
          assertThat(body.at("/points/0/qoder/ratio/reason").asText())
              .isEqualTo("no_eligible_input_tokens");
        });
  }

  @Test
  @DisplayName("agent contribution 返回 share 和 token segments")
  void agentContributionReturnsShares() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/agents/contribution");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("totalSessions").asLong()).isEqualTo(3);
          assertThat(body.get("totalPrompts").asLong()).isEqualTo(4);
          assertTokens(body.get("totalTokens"), ApiContractFixture.ALL);
          JsonNode claude = findByAgent(body.get("rows"), "claude_code");
          assertThat(claude.get("sessionCount").asLong()).isEqualTo(2);
          assertThat(claude.at("/tokens/total").asLong()).isEqualTo(3250);
          assertThat(claude.get("sessionShare").asDouble()).isCloseTo(200.0 / 3.0, EPSILON);
          JsonNode codex = findByAgent(body.get("rows"), "codex");
          assertThat(codex.get("sessionCount").asLong()).isEqualTo(1);
          assertThat(codex.at("/tokens/total").asLong()).isEqualTo(800);
          JsonNode qoder = findByAgent(body.get("rows"), "qoder");
          assertThat(qoder.get("sessionCount").asLong()).isEqualTo(0);
          assertThat(qoder.at("/tokens/total").asLong()).isEqualTo(0);
        });
  }

  @Test
  @DisplayName("agent deep-dive 只返回目标 agent 的 model efficiency")
  void agentDeepDiveFiltersEfficiencyRows() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/agents/claude-code/deep-dive");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/agent").asText()).isEqualTo("claude-code");
          assertThat(body.get("rows")).hasSize(1);
          assertThat(body.at("/rows/0/agent").asText()).isEqualTo("claude_code");
          assertThat(body.at("/rows/0/model").asText()).isEqualTo("claude-sonnet-4.5");
          assertThat(body.at("/rows/0/sessionCount").asLong()).isEqualTo(2);
          assertThat(body.at("/rows/0/avgTokensPerSession").asLong()).isEqualTo(1625);
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
    assertThat(tokens.get("total").asLong())
        .isEqualTo(
            tokens.get("fresh").asLong()
                + tokens.get("cacheRead").asLong()
                + tokens.get("cacheWrite").asLong()
                + tokens.get("output").asLong());
  }

  private static long sum(JsonNode points, String field) {
    long total = 0;
    for (JsonNode point : points) {
      total += point.get(field).asLong();
    }
    return total;
  }

  private static long sumNested(JsonNode points, String objectField, String field) {
    long total = 0;
    for (JsonNode point : points) {
      total += point.get(objectField).get(field).asLong();
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
