package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class TokenProvenanceResourceApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  @TempDir Path tempDir;
  private IndexConnection connection;

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("synthetic-provenance.db");
    connection =
        IndexConnection.create(DriverManager.getConnection(url), PragmaConfig.DEFAULTS, url);
    IndexSchema.ensureSchema(connection.writerConnection());
    ApiContractFixture.insertThreeSessionFixture(connection);
    LocalDate firstDay = LocalDate.now(ZoneOffset.UTC).minusDays(2);
    try (var statement =
        connection
            .writerConnection()
            .prepareStatement(
                """
                UPDATE sessions SET
                  started_at = (CASE WHEN session_key = 'claude_code:s-alpha-002'
                                    THEN ? ELSE ? END) || substr(started_at, 11),
                  ended_at = (CASE WHEN session_key = 'claude_code:s-alpha-002'
                                  THEN ? ELSE ? END) || substr(ended_at, 11),
                  fresh_input_token_precision = 'provider_reported',
                  cache_read_token_precision = 'provider_reported',
                  cache_write_token_precision = 'provider_reported',
                  output_token_precision = 'provider_reported', token_contains_unknown = 0
                """)) {
      statement.setString(1, firstDay.plusDays(1).toString());
      statement.setString(2, firstDay.toString());
      statement.setString(3, firstDay.plusDays(1).toString());
      statement.setString(4, firstDay.toString());
      assertThat(statement.executeUpdate()).isEqualTo(3);
    }
    try (var statement = connection.writerConnection().createStatement()) {
      assertThat(
              statement.executeUpdate(
                  """
                  UPDATE sessions SET session_key = 'qoder:synthetic-estimated',
                    session_id = 'synthetic-estimated', agent = 'qoder', model = 'synthetic-estimate-model',
                    fresh_input_token_precision = 'estimated', output_token_precision = 'estimated',
                    cache_read_token_precision = 'unavailable', cache_write_token_precision = 'unavailable',
                    token_estimation_method = 'synthetic_context',
                    token_contains_estimated = 1, token_contains_unavailable = 1
                  WHERE session_key = 'codex:s-beta-001'
                  """))
          .isEqualTo(1);
    }
  }

  @AfterEach
  void close() {
    if (connection != null) connection.close();
  }

  @Test
  void cacheStatisticsUseOnlyMeasuredInputSessionsInTheRequestedScope() {
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/summary");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.at("/cacheReadStatistics/eligibleSessions").asLong()).isEqualTo(2);
          assertThat(body.at("/cacheReadStatistics/excludedSessions").asLong()).isEqualTo(1);
          assertThat(body.at("/cacheReadStatistics/basis").asText())
              .isEqualTo("provider_reported_input");
          response = client.get("/api/dashboard/summary?agent=qoder");
          assertThat(response.code()).isEqualTo(200);
          body = MAPPER.readTree(response.body().string());
          assertThat(body.at("/cacheReadStatistics/eligibleSessions").asLong()).isZero();
          assertThat(body.at("/cacheReadStatistics/p50SessionRatio").isNull()).isTrue();
          assertThat(body.at("/cacheReadStatistics/lowReadSessions").asLong()).isZero();
          assertThat(body.at("/cacheReadStatistics/excludedSessions").asLong()).isEqualTo(1);
        });
  }

  @Test
  void cacheHealthKeepsEachDayAndAgentEvidenceInItsOwnScope() {
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/trends/cache-health");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          JsonNode first = body.path("points").get(0);
          assertThat(first.at("/claudeCode/provenance/cacheRead").asText())
              .isEqualTo("provider_reported");
          assertThat(first.at("/qoder/provenance/cacheRead").asText()).isEqualTo("unavailable");
          assertThat(first.at("/qoder/ratio/value").isNull()).isTrue();
          assertThat(first.at("/codex/provenance/unknownSessionCount").asLong()).isZero();
          assertThat(body.at("/latestRatio/provenance/estimatedSessionCount").asLong()).isZero();
          assertThat(body.at("/latestRatio/reason").asText()).isEmpty();
          assertThat(body.at("/lowestRatio/provenance/estimatedSessionCount").asLong())
              .isEqualTo(1);
        });
  }

  @Test
  void latestUnavailableDayDoesNotSilentlyReturnEarlierRatio() throws Exception {
    try (var statement = connection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET fresh_input_token_precision = 'estimated',
            cache_read_token_precision = 'unavailable', cache_write_token_precision = 'unavailable',
            token_contains_estimated = 1, token_contains_unavailable = 1,
            cache_read_tokens = 0, cache_write_tokens = 0,
            total_tokens = fresh_input_tokens + output_tokens
          WHERE session_key = 'claude_code:s-alpha-002'
          """);
    }
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/trends/cache-health");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.at("/latestRatio/value").isNull()).isTrue();
          assertThat(body.at("/latestRatio/reason").asText())
              .isEqualTo("token_measurement_unavailable");
          assertThat(body.at("/latestRatio/provenance/estimatedSessionCount").asLong())
              .isEqualTo(1);
        });
  }

  @Test
  void efficiencyDoesNotTurnUnreportedCacheIntoMeasuredZero() {
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get("/api/dashboard/agents/efficiency");
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          JsonNode qoder = null;
          for (JsonNode row : body.path("rows")) {
            if ("qoder".equals(row.path("agent").asText())) qoder = row;
          }
          assertThat(qoder).isNotNull();
          assertThat(qoder.path("cacheReuseRatio").isNull()).isTrue();
          assertThat(qoder.path("cacheReuseReason").asText())
              .isEqualTo("token_measurement_unavailable");
          assertThat(qoder.at("/provenance/estimatedSessionCount").asLong()).isEqualTo(1);
        });
  }

  private WebCompositionRoot web() {
    return new WebCompositionRoot(
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            connection, new SchemaVersion(1)),
        WebConfig.defaults());
  }
}
