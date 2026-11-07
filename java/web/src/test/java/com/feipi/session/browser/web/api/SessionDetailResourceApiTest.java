package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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
import java.util.List;
import java.util.Map;
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
  void personalCompatibilityRowDoesNotReadUnpublishedSourceOrAdjacentChildren() throws Exception {
    Path raw = tempDir.resolve("synthetic-unpublished.jsonl");
    String usage =
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":1,\"output_tokens\":1,\"total_tokens\":2}}}}\n";
    java.nio.file.Files.writeString(raw, usage);
    indexConnection
        .writeQueue()
        .submit(
            connection -> {
              try (var statement = connection.createStatement()) {
                statement.executeUpdate(
                    "DELETE FROM session_artifacts WHERE session_key='claude_code:s-alpha-001'");
                statement.executeUpdate(
                    "UPDATE sessions SET content_measured=0 WHERE session_key='claude_code:s-alpha-001'");
                statement.executeUpdate(
                    "INSERT OR REPLACE INTO index_metadata(key,value,updated_at) VALUES('published_generation','synthetic-frozen',0)");
              }
              try (var statement =
                  connection.prepareStatement(
                      "UPDATE sessions SET file_path=? WHERE session_key='claude_code:s-alpha-001'")) {
                statement.setString(1, raw.toString());
                statement.executeUpdate();
              }
            })
        .join();
    JavalinTest.test(
        createWebRoot().app(),
        (testApp, client) -> {
          var firstResponse = client.get(ALPHA_URL + "/metrics");
          JsonNode first = MAPPER.readTree(firstResponse.body().string());
          assertThat(first.at("/parity/contentMeasured").asBoolean()).isFalse();
          assertThat(first.at("/parity/workloadCallsAvailable").asBoolean()).isFalse();
          assertThat(first.at("/parity/runHealth").asText()).isEqualTo("Unknown");
          java.nio.file.Files.writeString(
              raw, usage + usage.replace("\":1", "\":2").replace("\":2}", "\":4}"));
          java.nio.file.Files.writeString(
              tempDir.resolve("synthetic-child.jsonl"),
              "{\"type\":\"session_meta\",\"payload\":{\"id\":\"synthetic-child\",\"parent_thread_id\":\"s-alpha-001\"}}\n"
                  + usage);
          var secondResponse = client.get(ALPHA_URL + "/metrics");
          assertThat(secondResponse.headers().get("X-Session-Index-Generation"))
              .isEqualTo(firstResponse.headers().get("X-Session-Index-Generation"))
              .containsExactly("synthetic-frozen");
          assertThat(MAPPER.readTree(secondResponse.body().string())).isEqualTo(first);
        });
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
          // 该fixture索引行是4工具，但冻结制品只有main+child共2工具；详情必须选择制品。
          assertThat(body.get("toolCalls").asLong()).isEqualTo(2);
          assertThat(body.get("failedTools").asLong()).isEqualTo(1);
          assertThat(body.at("/parity/toolCalls").asLong()).isEqualTo(2);
          assertThat(body.at("/parity/failedTools").asLong()).isEqualTo(1);
          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.get("payloadCount").asLong()).isEqualTo(4);
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
          assertThat(body.at("/rounds/0/calls").size()).isEqualTo(1);
          assertThat(body.at("/rounds/0/toolCallIds/0").asText()).isEqualTo("tool-call-1");
          assertThat(body.at("/rounds/0/toolCallIds").size()).isEqualTo(1);
          assertTokens(body.at("/rounds/0/tokens"), 1000, 400, 100, 500, 2000);
          assertThat(body.at("/rounds/0/tokenShare").asDouble()).isCloseTo(1.0, EPSILON);
          assertThat(body.at("/rounds/0/callCount").asInt()).isEqualTo(1);
          assertThat(body.at("/rounds/0/toolCallCount").asInt()).isEqualTo(1);
          assertThat(body.at("/rounds/0/failedToolCount").asInt()).isEqualTo(1);
          assertThat(body.at("/rounds/0/failedToolCallIds/0").asText()).isEqualTo("tool-call-1");
          assertThat(body.at("/rounds/0/status").asText()).isEqualTo("failed");
          assertThat(body.at("/rounds/0/signals/0").asText()).isEqualTo("Failed");
          assertThat(body.at("/rounds/0/signals").toString()).contains("Subagent");
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
          assertThat(standardBody.get("payloadCount").asLong()).isEqualTo(4);
          assertThat(standardBody.at("/payloads/0/payloadId").asText())
              .isEqualTo("main:req:alpha-call-1");
          assertThat(standardBody.at("/payloads/0/truncated").asBoolean()).isFalse();
          assertThat(standardBody.at("/payloads/0/status").asText()).isEqualTo("available");
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
    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  @Test
  @DisplayName("Round content 与工具 Input API 保留指令并与归因分离")
  void roundAndToolContentRoutesPreserveInstructions() throws Exception {
    Path path = tempDir.resolve("alpha-001.normalized.json");
    ObjectNode artifact = (ObjectNode) MAPPER.readTree(path.toFile());
    String command =
        "{\"command\":\"printf 'synthetic command'\",\"api_key\":\"synthetic-secret\"}";
    ((ObjectNode) artifact.at("/calls/0"))
        .set(
            "source_units",
            MAPPER.valueToTree(
                List.of(
                    Map.of("role", "user", "type", "text", "text", "inspect synthetic files"),
                    Map.of("role", "assistant", "type", "text", "text", "I will inspect them"),
                    Map.of(
                        "role",
                        "assistant",
                        "type",
                        "tool_use",
                        "id",
                        "tool-call-1",
                        "name",
                        "exec_command",
                        "input",
                        command))));
    ((ObjectNode) artifact.at("/tool_executions/0")).put("duration_ms", 0);
    MAPPER.writeValue(path.toFile(), artifact);

    JavalinTest.test(
        createWebRoot().app(),
        (app, client) -> {
          var response = client.get(ALPHA_URL + "/payload/round%3Aresp%3A1");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.path("kind").asText()).isEqualTo("llm_response");
          assertThat(body.path("status").asText()).isEqualTo("available");
          assertThat(body.path("truncated").asBoolean()).isFalse();
          assertThat(body.path("content").asText())
              .contains(
                  "I will inspect them",
                  "exec_command [tool-call-1]",
                  "printf 'synthetic command'",
                  "[REDACTED]")
              .doesNotContain("inspect synthetic files", "synthetic-secret");
          var request = client.get(ALPHA_URL + "/payload/round%3Areq%3A1");
          assertThat(request.code()).isEqualTo(200);
          assertThat(MAPPER.readTree(request.body().string()).path("content").asText())
              .contains("inspect synthetic files")
              .doesNotContain("synthetic command");
          var input = client.get(ALPHA_URL + "/payload/tool%3Ainput%3Atool-call-1");
          assertThat(input.code()).isEqualTo(200);
          JsonNode inputBody = MAPPER.readTree(input.body().string());
          assertThat(inputBody.path("kind").asText()).isEqualTo("tool_input");
          assertThat(inputBody.path("content").asText())
              .contains("printf 'synthetic command'", "[REDACTED]")
              .doesNotContain("synthetic-secret");
          var round = client.get(ALPHA_URL + "/round/1");
          assertThat(round.code()).isEqualTo(200);
          JsonNode detail = MAPPER.readTree(round.body().string());
          assertThat(detail.at("/round/tools/0/inputPreview").asText())
              .isEqualTo("printf 'synthetic command'");
          assertThat(detail.at("/round/tools/0/durationMs").isNull()).isTrue();
        });
  }

  @Test
  @DisplayName("子任务失败不回填到仅统计 MAIN 的 Round metrics")
  void subagentFailureDoesNotBecomeMainFailure() throws Exception {
    Path path = tempDir.resolve("alpha-001.normalized.json");
    ObjectNode artifact = (ObjectNode) MAPPER.readTree(path.toFile());
    ((ObjectNode) artifact.at("/tool_executions/0")).remove("status");
    ((ObjectNode) artifact.at("/tool_executions/1")).put("status", "error: exit 1");
    MAPPER.writeValue(path.toFile(), artifact);

    JavalinTest.test(
        createWebRoot().app(),
        (app, client) -> {
          var response = client.get(ALPHA_URL + "/rounds");
          assertThat(response.code()).isEqualTo(200);
          JsonNode round = MAPPER.readTree(response.body().string()).at("/rounds/0");
          assertThat(round.path("failedToolCount").asInt()).isZero();
          assertThat(round.path("status").asText()).isEqualTo("ok");
          assertThat(round.path("signals").toString()).doesNotContain("Failed");
          assertThat(round.at("/parity/hasIssues").asBoolean()).isFalse();
        });
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
