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

/** Session Detail resource APIs 的契约测试。 */
@DisplayName("Session Detail resource APIs")
class SessionDetailResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Offset<Double> EPSILON = Offset.offset(0.0001);
  private static final String ALPHA_URL = "/api/sessions/claude_code/s-alpha-001";

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("session-detail-resource-api-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    ApiContractFixture.insertThreeSessionFixture(indexConnection);
    ApiContractFixture.insertNormalizedArtifactForAlpha(indexConnection, tempDir);
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("meta 返回 session/project/artifact 原始字段")
  void metaReturnsSessionFields() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_URL + "/meta");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/agent").asText()).isEqualTo("claude_code");
          assertThat(body.get("sessionKey").asText()).isEqualTo("claude_code:s-alpha-001");
          assertThat(body.get("title").asText()).isEqualTo("Alpha refactor dashboard");
          assertThat(body.get("projectKey").asText()).isEqualTo("/repo/alpha");
          assertThat(body.get("hasArtifact").asBoolean()).isTrue();
          assertThat(body.get("artifactSchemaVersion").asText()).isNotBlank();
        });
  }

  @Test
  @DisplayName("metrics 返回 token 四段和 round/payload 数")
  void metricsReturnsTokenSegments() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_URL + "/metrics");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertTokens(body.get("tokens"), 1000, 400, 100, 500, 2000);
          assertThat(body.get("toolCalls").asLong()).isEqualTo(4);
          assertThat(body.get("failedTools").asLong()).isEqualTo(1);
          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.get("payloadCount").asLong()).isEqualTo(2);
        });
  }

  @Test
  @DisplayName("diagnostics 返回结构化 anomaly 列表")
  void diagnosticsReturnAnomalies() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_URL + "/diagnostics");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("anomalyCount").asInt()).isGreaterThan(0);
          assertThat(body.get("maxSeverity").asText()).isIn("critical", "warning", "info");
          assertThat(body.at("/anomalies/0/type").asText()).isNotBlank();
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("rounds 返回 round tokenbar ratio 和调用索引")
  void roundsReturnTokenShare() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_URL + "/rounds");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.at("/rounds/0/roundIndex").asInt()).isEqualTo(1);
          assertThat(body.at("/rounds/0/calls/0").asText()).isEqualTo("alpha-call-1");
          assertThat(body.at("/rounds/0/toolCallIds/0").asText()).isEqualTo("tool-call-1");
          assertTokens(body.at("/rounds/0/tokens"), 1000, 400, 100, 500, 2000);
          assertThat(body.at("/rounds/0/tokenShare").asDouble()).isCloseTo(1.0, EPSILON);
          assertThat(body.at("/rounds/0/failedToolCount").asInt()).isEqualTo(1);
          assertThat(body.at("/rounds/0/failedToolCallIds/0").asText()).isEqualTo("tool-call-1");
          assertThat(body.at("/rounds/0/status").asText()).isEqualTo("failed");
          assertThat(body.at("/rounds/0/signals/0").asText()).isEqualTo("Failed");
        });
  }

  @Test
  @DisplayName("rounds 支持 trace_status=failed 过滤并回显 normalized filter")
  void roundsFilterFailedTraceStatus() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_URL + "/rounds?trace_status=failed");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/traceStatus").asText()).isEqualTo("failed");
          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.at("/rounds/0/status").asText()).isEqualTo("failed");
          assertThat(body.at("/rounds/0/signals/0").asText()).isEqualTo("Failed");
        });
  }

  @Test
  @DisplayName("payloads 返回 visibility/truncated contract")
  void payloadsReturnVisibilityContract() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var standard = client.get(ALPHA_URL + "/payloads");
          assertThat(standard.code()).isEqualTo(200);
          JsonNode standardBody = MAPPER.readTree(standard.body().string());
          assertThat(standardBody.at("/filters/visibility").asText()).isEqualTo("standard");
          assertThat(standardBody.get("payloadCount").asLong()).isEqualTo(2);
          assertThat(standardBody.at("/payloads/0/payloadId").asText())
              .isEqualTo("main:req:alpha-call-1");
          assertThat(standardBody.at("/payloads/0/truncated").asBoolean()).isTrue();
          assertThat(standardBody.at("/payloads/0/status").asText()).isEqualTo("hidden");
          assertThat(standardBody.at("/payloads/0/apiUrl").asText())
              .isEqualTo("/api/sessions/claude_code/s-alpha-001/payload/main%3Areq%3Aalpha-call-1");

          var full = client.get(ALPHA_URL + "/payloads?visibility=full");
          assertThat(full.code()).isEqualTo(200);
          JsonNode fullBody = MAPPER.readTree(full.body().string());
          assertThat(fullBody.at("/filters/visibility").asText()).isEqualTo("full");
          assertThat(fullBody.at("/payloads/0/truncated").asBoolean()).isFalse();
          assertThat(fullBody.at("/payloads/0/status").asText()).isEqualTo("available");
        });
  }

  @Test
  @DisplayName("payloads 支持 status=failed 过滤并返回显式 no_results state")
  void payloadsFilterFailedStatus() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_URL + "/payloads?status=failed");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.at("/filters/payloadStatus").asText()).isEqualTo("failed");
          assertThat(body.get("payloadCount").asLong()).isEqualTo(0);
          assertThat(body.get("payloads")).isEmpty();
          assertThat(body.at("/state/kind").asText()).isEqualTo("no_results");
        });
  }

  @Test
  @DisplayName("不存在 session 返回 JSON 404")
  void missingSessionReturnsJson404() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/sessions/claude_code/no-such-session/meta");
          assertThat(response.code()).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).contains("not_found");
          assertThat(body).contains("session not found");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static void assertTokens(
      JsonNode tokens, long fresh, long cacheRead, long cacheWrite, long output, long total) {
    assertThat(tokens.get("fresh").asLong()).isEqualTo(fresh);
    assertThat(tokens.get("cacheRead").asLong()).isEqualTo(cacheRead);
    assertThat(tokens.get("cacheWrite").asLong()).isEqualTo(cacheWrite);
    assertThat(tokens.get("output").asLong()).isEqualTo(output);
    assertThat(tokens.get("total").asLong()).isEqualTo(total);
    assertThat(tokens.get("total").asLong()).isEqualTo(fresh + cacheRead + cacheWrite + output);
  }
}
