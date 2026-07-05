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

/** static Glossary resource APIs 的契约测试。 */
@DisplayName("Glossary resource APIs")
class GlossaryResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("glossary-resource-api-test.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("summary 固化四个 glossary section 计数")
  void summaryReturnsSectionCounts() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/glossary/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("tokenTypeCount").asLong()).isEqualTo(6);
          assertThat(body.get("derivedMetricCount").asLong()).isEqualTo(7);
          assertThat(body.get("providerMappingCount").asLong()).isEqualTo(5);
          assertThat(body.get("roundSignalCount").asLong()).isEqualTo(6);
          assertThat(body.at("/state/kind").asText()).isEqualTo("ready");
        });
  }

  @Test
  @DisplayName("token-types 暴露 token 组件和 total 公式")
  void tokenTypesReturnFormulaContract() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/glossary/token-types");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());

          assertThat(body.get("count").asLong()).isEqualTo(6);
          assertThat(keys(body.get("terms")))
              .contains("fresh", "cache_read", "cache_write", "output", "total_tokens");
          assertThat(findTerm(body.get("terms"), "total_tokens").get("formula").asText())
              .isEqualTo("Fresh + Cache Read + Cache Write + Output");
        });
  }

  @Test
  @DisplayName("provider-mapping 和 round-signals 不依赖 Playwright 校验完整性")
  void providerMappingAndRoundSignalsReturnKeys() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          JsonNode providers =
              MAPPER.readTree(client.get("/api/glossary/provider-mapping").body().string());
          assertThat(keys(providers.get("terms")))
              .contains("anthropic", "openai", "codex", "qoder", "not_reported");
          assertThat(findTerm(providers.get("terms"), "openai").get("providerFields"))
              .hasSizeGreaterThanOrEqualTo(4);

          var providerAlias = client.get("/api/glossary/provider-mappings");
          assertThat(providerAlias.code()).isEqualTo(200);
          JsonNode aliasBody = MAPPER.readTree(providerAlias.body().string());
          assertThat(keys(aliasBody.get("terms"))).contains("anthropic", "openai");

          JsonNode signals =
              MAPPER.readTree(client.get("/api/glossary/round-signals").body().string());
          assertThat(keys(signals.get("terms")))
              .contains("trace_id", "turn_id", "tool_call_id", "failure", "subagent");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  private static java.util.List<String> keys(JsonNode terms) {
    java.util.List<String> result = new java.util.ArrayList<>();
    terms.forEach(node -> result.add(node.get("key").asText()));
    return result;
  }

  private static JsonNode findTerm(JsonNode terms, String key) {
    for (JsonNode term : terms) {
      if (key.equals(term.get("key").asText())) {
        return term;
      }
    }
    throw new AssertionError("glossary term not found: " + key);
  }
}
