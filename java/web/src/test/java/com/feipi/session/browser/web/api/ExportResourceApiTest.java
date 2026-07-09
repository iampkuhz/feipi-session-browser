package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
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

/** export manifest/data-bundle APIs 的契约测试。 */
@DisplayName("Export resource APIs")
class ExportResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String ALPHA_EXPORT = "/api/export/session/claude_code/s-alpha-001";

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("export-resource-api-test.db");
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
  @DisplayName("manifest 返回支持格式、URL 和离线能力")
  void manifestReturnsExportFormats() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_EXPORT + "/manifest");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("sessionKey").asText()).isEqualTo("claude_code:s-alpha-001");
          assertThat(body.get("visibility").asText()).isEqualTo("standard");
          assertThat(body.get("hasArtifact").asBoolean()).isTrue();
          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.get("payloadCount").asLong()).isEqualTo(4);
          assertThat(body.get("maxBytes").asLong()).isGreaterThan(1_000_000);
          assertThat(body.get("maxSizeBytes").asLong()).isEqualTo(body.get("maxBytes").asLong());
          assertThat(body.get("estimatedSizeBytes").asLong())
              .isLessThan(body.get("maxSizeBytes").asLong());
          assertThat(body.get("embeddedDataCapable").asBoolean()).isTrue();
          assertThat(body.get("offlineInteractionSupported").asBoolean()).isTrue();
          assertThat(values(body.get("formats"), "format")).containsExactly("html", "mhtml");
          assertThat(body.at("/formats/0/href").asText())
              .isEqualTo("/sessions/claude_code/s-alpha-001/export.html?visibility=standard");
          assertThat(body.at("/formats/1/contentType").asText()).isEqualTo("multipart/related");
          assertThat(body.at("/formats/1/offlineCapable").asBoolean()).isTrue();
        });
  }

  @Test
  @DisplayName("manifest 支持按 format 过滤导出能力")
  void manifestSupportsFormatFilter() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_EXPORT + "/manifest?format=html");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(values(body.get("formats"), "format")).containsExactly("html");
          assertThat(body.at("/formats/0/contentType").asText()).contains("text/html");
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("manifest 对 unsupported format 返回 400 JSON error")
  void manifestUnsupportedFormatReturns400() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_EXPORT + "/manifest?format=pdf");
          assertThat(response.code()).isEqualTo(400);
          String body = response.body().string();
          assertThat(body).contains("unsupported_format");
          assertThat(body).doesNotContain("state-panel");
        });
  }

  @Test
  @DisplayName("manifest 超出 max_bytes 时返回 too_large state 且不声明 ready formats")
  void manifestTooLargeReturnsExplicitState() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_EXPORT + "/manifest?max_bytes=1");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("estimatedSizeBytes").asLong())
              .isGreaterThan(body.get("maxSizeBytes").asLong());
          assertThat(body.get("formats")).isEmpty();
          assertThat(body.at("/state/kind").asText()).isEqualTo("too_large");
          assertThat(body.at("/state/reason").asText()).isEqualTo("export_size_limit_exceeded");
        });
  }

  @Test
  @DisplayName("data-bundle 返回离线导出所需数据骨架")
  void dataBundleReturnsOfflineDataShape() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get(ALPHA_EXPORT + "/data-bundle?visibility=full");
          String responseBody = response.body().string();
          assertThat(response.code()).as(responseBody).isEqualTo(200);
          JsonNode body = MAPPER.readTree(responseBody);

          assertThat(body.get("visibility").asText()).isEqualTo("full");
          assertThat(body.at("/tokens/total").asLong()).isEqualTo(2000);
          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.at("/rounds/0/tokens/total").asLong()).isEqualTo(2000);
          assertThat(body.at("/rounds/0/signals/0").asText()).isEqualTo("Failed");
          assertThat(body.at("/rounds/0/signals/1").asText()).isEqualTo("Subagent");
          assertThat(body.get("payloadCount").asLong()).isEqualTo(4);
          assertThat(body.at("/payloads/0/truncated").asBoolean()).isFalse();
          assertThat(body.at("/payloads/0/status").asText()).isEqualTo("available");
          assertThat(body.at("/payloads/0/apiUrl").asText())
              .isEqualTo("/api/sessions/claude_code/s-alpha-001/payload/main%3Areq%3Aalpha-call-1");
          assertThat(body.get("anomalyCount").asInt()).isGreaterThan(0);
        });
  }

  @Test
  @DisplayName("manifest 对不存在 session 返回 JSON 404")
  void manifestMissingSessionReturnsJson404() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/export/session/claude_code/no-such/manifest");
          assertThat(response.code()).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).contains("not_found");
          assertThat(body).contains("session not found");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = com.feipi.session.browser.web.WebTestComposition.queryRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static java.util.List<String> values(JsonNode nodes, String field) {
    java.util.List<String> result = new java.util.ArrayList<>();
    nodes.forEach(node -> result.add(node.get(field).asText()));
    return result;
  }
}
