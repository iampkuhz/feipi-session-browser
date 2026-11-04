package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import com.feipi.session.browser.web.WebTestComposition;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** synthetic 端点证明计时来源与数值一起传播，不信任旧推算执行秒数。 */
class SessionTimingResourceApiTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String METRICS = "/api/sessions/claude_code/s-alpha-001/metrics";
  @TempDir Path tempDir;
  private IndexConnection connection;

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("synthetic-timing.db");
    connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url);
    IndexSchema.withDefaults().ensureSchema(connection.writerConnection());
    ApiContractFixture.insertThreeSessionFixture(connection);
    ApiContractFixture.insertNormalizedArtifactForAlpha(connection, tempDir);
  }

  @AfterEach
  void close() {
    if (connection != null) connection.close();
  }

  @Test
  void oldInferredExecutionSecondsDoNotBecomeMeasuredModelOrActiveTime() throws Exception {
    try (var statement = connection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET timing_json = '{"activeTaskSeconds":900,"activeTaskPrecision":"unknown",
            "modelExecutionSeconds":900,"toolExecutionSeconds":900}'
          """);
    }
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get(METRICS);
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.path("modelExecutionSeconds").isNull()).isTrue();
          assertThat(body.path("toolExecutionSeconds").isNull()).isTrue();
          assertThat(body.at("/timing/activeTaskPrecision").asText()).isEqualTo("unknown");
          assertThat(body.at("/timing/modelExecutionPrecision").asText()).isEqualTo("unknown");
          assertThat(body.at("/parity/modelTimeAvailable").asBoolean()).isFalse();
          assertThat(body.at("/parity/activeTimeAvailable").asBoolean()).isFalse();
          assertThat(body.path("parity").has("waitingSeconds")).isFalse();
          response = client.get("/api/sessions/rows");
          assertThat(response.code()).isEqualTo(200);
          for (JsonNode row : MAPPER.readTree(response.body().string()).path("rows")) {
            assertThat(row.path("processSeconds").isNull()).isTrue();
          }
        });
  }

  @Test
  void mainTaskWindowsAndMeasuredZeroRemainIndependentFromModelAndToolUnknown() throws Exception {
    try (var statement =
        connection
            .writerConnection()
            .prepareStatement(
                "UPDATE sessions SET timing_json = ? WHERE session_key ="
                    + " 'claude_code:s-alpha-001'")) {
      statement.setString(
          1,
          """
          {"wallSeconds":86400,"wallPrecision":"measured",
           "activeTaskSeconds":120,"activeTaskPrecision":"measured",
           "activeTaskBasis":"main_task_windows","modelExecutionSeconds":0,
           "modelExecutionPrecision":"measured","toolExecutionPrecision":"unknown",
           "agentTurnPrecision":"unknown","completedTaskCount":2,
           "incompleteTaskCount":0,"abortedTaskCount":0}
          """);
      assertThat(statement.executeUpdate()).isEqualTo(1);
    }
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get(METRICS);
          assertThat(response.code()).isEqualTo(200);
          JsonNode body = MAPPER.readTree(response.body().string());
          assertThat(body.path("modelExecutionSeconds").asDouble()).isZero();
          assertThat(body.path("toolExecutionSeconds").isNull()).isTrue();
          assertThat(body.at("/timing/activeTaskSeconds").asDouble()).isEqualTo(120);
          assertThat(body.at("/parity/activeSeconds").asDouble()).isEqualTo(120);
          assertThat(body.at("/parity/nonTaskWallSeconds").asDouble()).isEqualTo(86280);
          assertThat(body.at("/parity/modelTimeAvailable").asBoolean()).isTrue();
          assertThat(body.at("/parity/toolTimeAvailable").asBoolean()).isFalse();
          response = client.get("/api/sessions/rows");
          assertThat(response.code()).isEqualTo(200);
          JsonNode selected = null;
          for (JsonNode row : MAPPER.readTree(response.body().string()).path("rows")) {
            if ("s-alpha-001".equals(row.path("sessionId").asText())) selected = row;
          }
          assertThat(selected).isNotNull();
          assertThat(selected.path("processSeconds").asDouble()).isEqualTo(120);
          assertThat(selected.at("/timing/activeTaskBasis").asText())
              .isEqualTo("main_task_windows");
        });
  }

  private WebCompositionRoot web() {
    return new WebCompositionRoot(
        WebTestComposition.queryRoot(connection, new SchemaVersion(1)), WebConfig.defaults());
  }

  @Test
  void taskActiveSortingUsesDisplayedValuesAndKeepsUnknownLastInBothDirections() throws Exception {
    try (var statement = connection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET timing_json = '{"activeTaskSeconds":0,"activeTaskPrecision":"measured"}'
          WHERE session_key = 'claude_code:s-alpha-001'
          """);
      statement.executeUpdate(
          """
          UPDATE sessions SET timing_json = '{"activeTaskSeconds":120,"activeTaskPrecision":"partial"}'
          WHERE session_key = 'claude_code:s-alpha-002'
          """);
    }
    JavalinTest.test(
        web().app(),
        (app, client) -> {
          var response = client.get("/api/sessions/rows?sort=process-time&dir=asc");
          assertThat(response.code()).isEqualTo(200);
          JsonNode rows = MAPPER.readTree(response.body().string()).path("rows");
          assertThat(rows.get(0).path("sessionId").asText()).isEqualTo("s-alpha-001");
          assertThat(rows.get(1).path("sessionId").asText()).isEqualTo("s-alpha-002");
          assertThat(rows.get(2).path("processSeconds").isNull()).isTrue();
          response = client.get("/api/sessions/rows?sort=process-time&dir=desc");
          assertThat(response.code()).isEqualTo(200);
          rows = MAPPER.readTree(response.body().string()).path("rows");
          assertThat(rows.get(0).path("sessionId").asText()).isEqualTo("s-alpha-002");
          assertThat(rows.get(1).path("sessionId").asText()).isEqualTo("s-alpha-001");
          assertThat(rows.get(2).path("processSeconds").isNull()).isTrue();
        });
  }
}
