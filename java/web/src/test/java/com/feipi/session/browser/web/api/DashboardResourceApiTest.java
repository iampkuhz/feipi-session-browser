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
import java.time.LocalDate;
import java.time.ZoneOffset;
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
  private String firstFixtureDay;
  private String secondFixtureDay;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("dashboard-resource-api-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    ApiContractFixture.insertThreeSessionFixture(indexConnection);

    // 趋势查询使用 SQLite 的 UTC 当前窗口；仅移动本测试日期，保留分组、时刻和精确指标。
    LocalDate firstDay = LocalDate.now(ZoneOffset.UTC).minusDays(2);
    firstFixtureDay = firstDay.toString();
    secondFixtureDay = firstDay.plusDays(1).toString();
    try (var statement =
        indexConnection
            .writerConnection()
            .prepareStatement(
                """
                UPDATE sessions
                SET started_at =
                    (CASE WHEN session_key = 'claude_code:s-alpha-002'
                          THEN ? ELSE ? END) || substr(started_at, 11),
                    fresh_input_token_precision = 'provider_reported',
                    cache_read_token_precision = 'provider_reported',
                    cache_write_token_precision = 'provider_reported',
                    output_token_precision = 'provider_reported', token_contains_unknown = 0,
                    ended_at =
                    (CASE WHEN session_key = 'claude_code:s-alpha-002'
                          THEN ? ELSE ? END) || substr(ended_at, 11)
                WHERE session_key IN
                    ('claude_code:s-alpha-001', 'codex:s-beta-001', 'claude_code:s-alpha-002')
                """)) {
      statement.setString(1, secondFixtureDay);
      statement.setString(2, firstFixtureDay);
      statement.setString(3, secondFixtureDay);
      statement.setString(4, firstFixtureDay);
      assertThat(statement.executeUpdate()).isEqualTo(3);
    }
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("已上报输入的 Dashboard SSR 等待当前粒度数据，不冒显 daily ratio badge")
  void reportedInputKeepsCacheRatioBadge() {
    JavalinTest.test(
        createWebRoot().app(),
        (testApp, client) -> {
          var response = client.get("/dashboard");
          assertThat(response.code()).isEqualTo(200);
          assertThat(response.body().string())
              .containsPattern("(?s)data-kpi-badge-tooltip=\"Cache Read Ratio\"[^>]*>N/A</span>");
        });
  }

  @Test
  @DisplayName("输入来源未知时 Dashboard SSR 不显示精确 cache ratio 变化")
  void unknownInputDoesNotInventCacheRatioDelta() throws Exception {
    try (var statement = indexConnection.writerConnection().createStatement()) {
      assertThat(
              statement.executeUpdate(
                  "UPDATE sessions SET cache_read_token_precision = 'unknown',"
                      + " token_contains_unknown = 1 WHERE session_key = 'codex:s-beta-001'"))
          .isEqualTo(1);
    }
    JavalinTest.test(
        createWebRoot().app(),
        (testApp, client) -> {
          var response = client.get("/dashboard");
          assertThat(response.code()).isEqualTo(200);
          assertThat(response.body().string())
              .containsPattern("(?s)data-kpi-badge-tooltip=\"Cache Read Ratio\"[^>]*>N/A</span>");
        });
  }

  @Test
  @DisplayName("All 与各 agent 的 Day/Week/Month notes 明确 UTC 开始会话整段累计口径")
  void chartNotesFollowStartedCohortScopeAndGrain() {
    JavalinTest.test(
        createWebRoot().app(),
        (testApp, client) -> {
          for (String scope : new String[] {"all", "claude-code", "codex", "qoder"}) {
            String scopeLabel =
                switch (scope) {
                  case "claude-code" -> "Claude Code";
                  case "codex" -> "Codex";
                  case "qoder" -> "Qoder";
                  default -> "All agents";
                };
            for (String grain : new String[] {"day", "week", "month"}) {
              String grainLabel =
                  switch (grain) {
                    case "week" -> "ISO 周";
                    case "month" -> "自然月";
                    default -> "天";
                  };
              var response = client.get("/dashboard?agent=" + scope + "&grain=" + grain);
              assertThat(response.code()).isEqualTo(200);
              assertThat(response.body().string())
                  .contains("按 UTC 开始日，按" + grainLabel + "统计 " + scopeLabel + " 新增会话")
                  .contains("该批 " + scopeLabel + " 会话的整段累计 tokens")
                  .contains("该批 " + scopeLabel + " 会话的整段累计 user prompts")
                  .contains("平均 prompts 的分母为同一批开始会话中的 user 消息实测样本")
                  .contains("不是逐次真实消费日");
            }
          }
        });
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
  @DisplayName("summary 和 SSR 使用独立消息样本均值，不用内容覆盖或 legacy 总量作分母分子")
  void messageMeansAndCoverageRemainIndependentFromContentAndTotals() throws Exception {
    try (var statement = indexConnection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET content_measured=1,
            user_message_count=CASE session_key WHEN 'claude_code:s-alpha-001' THEN 0
              WHEN 'claude_code:s-alpha-002' THEN 6 ELSE 1000 END,
            assistant_message_count=CASE session_key WHEN 'claude_code:s-alpha-001' THEN 0
              WHEN 'claude_code:s-alpha-002' THEN 8 ELSE 1000 END,
            user_message_measured=CASE WHEN agent='claude_code' THEN 1 ELSE 0 END,
            assistant_message_measured=CASE WHEN agent='claude_code' THEN 1 ELSE 0 END
          """);
    }
    JavalinTest.test(
        createWebRoot().app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.at("/userMessageSampleCount").asLong()).isEqualTo(2);
          assertThat(body.at("/assistantMessageSampleCount").asLong()).isEqualTo(2);
          assertThat(body.at("/avgUserMessagesPerSession").asDouble()).isEqualTo(3);
          assertThat(body.at("/avgAssistantMessagesPerSession").asDouble()).isEqualTo(4);
          var page = client.get("/dashboard");
          assertThat(page.code()).isEqualTo(200);
          assertThat(page.body().string())
              .contains("user 消息测量样本 2 / 3", "assistant 消息测量样本 2 / 3")
              .containsPattern(
                  "(?s)Prompts / Session</span>\\s*<span"
                      + " class=\"metric-card__secondary-value\">3\\.0</span>")
              .containsPattern(
                  "(?s)Avg Assistant Messages</span>\\s*<span"
                      + " class=\"metric-card__secondary-value\">4\\.0</span>");
          var absent = client.get("/api/dashboard/summary?agent=codex");
          assertThat(absent.code()).isEqualTo(200);
          JsonNode unmeasured = MAPPER.readTree(absent.body().string());
          assertThat(unmeasured.at("/userMessageSampleCount").asLong()).isZero();
          assertThat(unmeasured.at("/assistantMessageSampleCount").asLong()).isZero();
          assertThat(unmeasured.at("/avgUserMessagesPerSession").isNull()).isTrue();
          assertThat(unmeasured.at("/avgAssistantMessagesPerSession").isNull()).isTrue();
        });
  }

  @Test
  @DisplayName("prompt trend 分别传递实测消息和与样本数，不把 unknown 或原总量当均值依据")
  void promptTrendPreservesMessageMeasurementWeightsPerCohortAndAgent() throws Exception {
    try (var statement = indexConnection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET
            user_message_count=CASE session_key WHEN 'claude_code:s-alpha-001' THEN 0
              WHEN 'claude_code:s-alpha-002' THEN 6 ELSE 1000 END,
            user_message_measured=CASE WHEN agent='claude_code' THEN 1 ELSE 0 END
          """);
    }
    JavalinTest.test(
        createWebRoot().app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/trends/prompts?grain=week");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.at("/points/0/totalPrompts").asLong()).isEqualTo(1000);
          assertThat(body.at("/points/0/measuredUserMessages").asLong()).isZero();
          assertThat(body.at("/points/0/userMessageSampleCount").asLong()).isEqualTo(1);
          assertThat(body.at("/points/0/claudeUserMessageSampleCount").asLong()).isEqualTo(1);
          assertThat(body.at("/points/0/codexUserMessageSampleCount").asLong()).isZero();
          assertThat(body.at("/points/1/measuredUserMessages").asLong()).isEqualTo(6);
          assertThat(body.at("/points/1/userMessageSampleCount").asLong()).isEqualTo(1);
          assertThat(body.at("/points/1/claudeMeasuredUserMessages").asLong()).isEqualTo(6);
          var unknown = client.get("/api/dashboard/trends/prompts?agent=codex");
          assertThat(unknown.code()).isEqualTo(200);
          JsonNode scoped = MAPPER.readTree(unknown.body().string());
          assertThat(scoped.at("/points/0/userMessageSampleCount").asLong()).isZero();
          assertThat(scoped.at("/points/0/measuredUserMessages").asLong()).isZero();
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
          assertThat(body.at("/points/0/date").asText()).isEqualTo(firstFixtureDay);
          assertThat(body.at("/points/0/totalCount").asLong()).isEqualTo(2);
          assertThat(body.at("/points/1/date").asText()).isEqualTo(secondFixtureDay);
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
  @DisplayName("agent efficiency 返回全局 model efficiency rows")
  void agentEfficiencyReturnsAllModelRows() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/dashboard/agents/efficiency");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/agent").asText()).isEqualTo("all");
          assertThat(body.get("rows")).hasSize(2);
          JsonNode claude = findEfficiencyRow(body.get("rows"), "claude_code", "claude-sonnet-4.5");
          assertThat(claude.get("sessionCount").asLong()).isEqualTo(2);
          assertThat(claude.get("avgTokensPerSession").asLong()).isEqualTo(1625);
          JsonNode codex = findEfficiencyRow(body.get("rows"), "codex", "gpt-5.4");
          assertThat(codex.get("sessionCount").asLong()).isEqualTo(1);
          assertThat(codex.get("avgTokensPerSession").asLong()).isEqualTo(800);
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

  private static JsonNode findEfficiencyRow(JsonNode rows, String agent, String model) {
    for (JsonNode row : rows) {
      if (agent.equals(row.get("agent").asText()) && model.equals(row.get("model").asText())) {
        return row;
      }
    }
    throw new AssertionError("efficiency row not found: " + agent + " / " + model);
  }
}
