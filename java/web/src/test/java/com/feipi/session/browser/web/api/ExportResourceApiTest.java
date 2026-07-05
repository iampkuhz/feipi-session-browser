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
          assertThat(body.get("payloadCount").asLong()).isEqualTo(2);
          assertThat(body.get("maxBytes").asLong()).isGreaterThan(1_000_000);
          assertThat(values(body.get("formats"), "format")).containsExactly("html", "mhtml");
          assertThat(body.at("/formats/0/href").asText())
              .isEqualTo("/sessions/claude_code/s-alpha-001/export.html?visibility=standard");
          assertThat(body.at("/formats/1/contentType").asText()).isEqualTo("multipart/related");
          assertThat(body.at("/formats/1/offlineCapable").asBoolean()).isTrue();
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
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("visibility").asText()).isEqualTo("full");
          assertThat(body.at("/tokens/total").asLong()).isEqualTo(2000);
          assertThat(body.get("roundCount").asLong()).isEqualTo(1);
          assertThat(body.at("/rounds/0/tokens/total").asLong()).isEqualTo(2000);
          assertThat(body.get("payloadCount").asLong()).isEqualTo(2);
          assertThat(body.at("/payloads/0/truncated").asBoolean()).isFalse();
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
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static java.util.List<String> values(JsonNode nodes, String field) {
    java.util.List<String> result = new java.util.ArrayList<>();
    nodes.forEach(node -> result.add(node.get(field).asText()));
    return result;
  }
}
