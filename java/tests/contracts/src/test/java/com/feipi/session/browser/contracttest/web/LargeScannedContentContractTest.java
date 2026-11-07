package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.contracttest.support.ContractTestComposition;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.Migration;
import com.feipi.session.browser.index.store.sqlite.schema.MigrationRunner;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.io.BufferedWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 验证超过旧容量的合成原始事件经真实扫描和磁盘重开后仍完整保留，不靠内存对象绕过存储边界。 */
class LargeScannedContentContractTest {
  private static final String SESSION_ID = "22222222-2222-4222-8222-222222222222";
  private static final int CALLS = 10_234;
  private static final int CALLS_PER_ROUND = 128;

  @TempDir Path tempDir;

  @ParameterizedTest
  @ValueSource(booleans = {false, true})
  void completeLargeSessionSurvivesFullAndIncrementalScan(boolean incremental) throws Exception {
    Path source = tempDir.resolve("source");
    writeSource(source);
    var config =
        new ScanConfig(
            List.of(new ScanConfig.SourceEntry(new CodexSourceAdapter(), source)),
            tempDir.resolve("artifacts"),
            incremental ? Set.of("codex") : Set.of(),
            1);
    String jdbcUrl = "jdbc:sqlite:" + tempDir.resolve("index.db").toAbsolutePath();
    try (var connection = DriverManager.getConnection(jdbcUrl)) {
      SqliteTestHelper.configureConnection(connection);
      if (incremental) {
        new MigrationRunner(
                Migration.allMigrations().stream()
                    .filter(migration -> migration.version().version() <= 6)
                    .toList())
            .applyAll(connection);
        try (var statement = connection.createStatement()) {
          statement.executeUpdate(
              "INSERT INTO sessions (session_key, agent, session_id, project_key, ended_at, round_count, llm_call_count)"
                  + " VALUES ('claude_code:legacy','claude_code','legacy','','',2,70)");
        }
        var schema = IndexSchema.withDefaults();
        assertThat(schema.ensureSchema(connection)).containsExactly(IndexSchema.CURRENT_VERSION);
        assertThat(schema.ensureSchema(connection)).isEmpty();
      }
      var writer = SqliteTestHelper.createIndexWriter(connection);
      if (incremental) {
        var result = new IncrementalScanEngine().scan(writer, config);
        assertThat(result.errorCount()).as("scan issues: %s", result.issues()).isZero();
        assertThat(result.successCount()).isEqualTo(1);
        try (var statement = connection.createStatement();
            var legacy =
                statement.executeQuery(
                    "SELECT round_count, llm_call_count, model_call_count "
                        + "FROM sessions WHERE session_key = 'claude_code:legacy'")) {
          assertThat(legacy.next()).isTrue();
          assertThat(legacy.getLong("round_count")).isEqualTo(2);
          assertThat(legacy.getLong("llm_call_count")).isEqualTo(70);
          assertThat(legacy.getObject("model_call_count")).isNull();
        }
      } else {
        var result = new FullScanEngine().scan(writer, config);
        assertThat(result.errorCount()).as("scan issues: %s", result.issues()).isZero();
        assertThat(result.successCount()).isEqualTo(1);
      }
    }

    // 使用新数据库连接和新加载器重开内容，确保验证不依赖扫描期间保留的内存对象。
    try (var connection = DriverManager.getConnection(jdbcUrl);
        var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT s.round_count, s.model_call_count, s.total_tokens, s.user_message_count, a.path "
                    + "FROM sessions s JOIN session_artifacts a ON a.session_key=s.session_key "
                    + "WHERE a.artifact_type='normalized'")) {
      assertThat(rows.next()).isTrue();
      assertThat(rows.getLong("round_count")).isEqualTo(CALLS);
      assertThat(rows.getLong("model_call_count")).isEqualTo(CALLS);
      assertThat(rows.getLong("total_tokens")).isEqualTo(CALLS * 11L);
      assertThat(rows.getLong("user_message_count")).isEqualTo(CALLS);
      var content = NormalizedArtifactLoader.open(Path.of(rows.getString("path")));
      assertThat(content.header().totals().get("calls")).isEqualTo(CALLS);
      long count = 0;
      long tokens = 0;
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          for (var call : cursor.next().calls()) {
            int index = (int) count++;
            assertThat(call.callIndex()).isEqualTo(index + 1);
            assertThat(call.callId()).isEqualTo("token_usage_record:response-" + index);
            assertThat(call.turnId()).contains("turn-" + index / CALLS_PER_ROUND);
            assertThat(call.sourceUnits().stream().map(unit -> unit.get("text")))
                .contains("synthetic-question-" + index, "synthetic-answer-" + index);
            tokens += call.usage().total();
          }
        }
      }
      assertThat(count).isEqualTo(CALLS);
      assertThat(tokens).isEqualTo(CALLS * 11L);
      assertThat(rows.next()).isFalse();
    }
    verifyHttp(jdbcUrl);
  }

  private static void verifyHttp(String jdbcUrl) throws Exception {
    var json = new ObjectMapper();

    try (var index =
        IndexConnection.create(
            DriverManager.getConnection(jdbcUrl), PragmaConfig.DEFAULTS, jdbcUrl)) {
      var web =
          new WebCompositionRoot(
              ContractTestComposition.queryRoot(index, new SchemaVersion(1)), WebConfig.defaults());
      JavalinTest.test(
          web.app(),
          (app, client) -> {
            String api = "/api/sessions/codex/" + SESSION_ID;
            var metricsResponse = client.get(api + "/metrics");
            assertThat(metricsResponse.code()).isEqualTo(200);
            var metrics = json.readTree(metricsResponse.body().string());
            assertThat(metrics.at("/tokens/total").asLong()).isEqualTo(CALLS * 11L);
            assertThat(metrics.path("roundCount").asInt()).isEqualTo(CALLS);
            assertThat(metrics.path("payloadCount").asLong()).isEqualTo(CALLS * 2L);
            assertThat(metrics.at("/parity/workloadCalls").asLong()).isEqualTo(CALLS);

            int seenRounds = 0;
            String next = null;
            do {
              var response =
                  client.get(api + "/rounds?limit=37" + (next == null ? "" : "&cursor=" + next));
              assertThat(response.code()).isEqualTo(200);
              var page = json.readTree(response.body().string());
              assertThat(page.path("total").asInt()).isEqualTo(CALLS);
              assertThat(page.path("modelCallCount").asInt()).isEqualTo(CALLS);
              assertThat(page.path("recordGroupCount").asInt()).isZero();
              for (var round : page.path("rounds")) {
                assertThat(round.path("roundIndex").asInt()).isEqualTo(++seenRounds);
                assertThat(round.path("callCount").asInt()).isEqualTo(1);
                assertThat(round.at("/tokens/total").asLong()).isEqualTo(11L);
                assertThat(round.at("/tokens/provenance/freshInput").asText())
                    .isEqualTo("provider_reported");
              }
              next = page.path("nextCursor").isNull() ? null : page.path("nextCursor").asText();
            } while (next != null && seenRounds < 74);
            assertThat(seenRounds).isEqualTo(74);
            assertThat(next).isNotNull();

            var last = client.get(api + "/round/" + CALLS + "?limit=17");
            assertThat(last.code()).isEqualTo(200);
            var members = json.readTree(last.body().string());
            assertThat(members.at("/round/calls").size()).isEqualTo(1);
            assertThat(members.at("/round/calls/0/callKey").asText()).isEqualTo("C" + CALLS);
            assertThat(members.at("/round/calls/0/callId").asText())
                .isEqualTo("token_usage_record:response-" + (CALLS - 1));
            assertThat(members.path("nextCursor").isNull()).isTrue();

            var payload =
                client.get(api + "/payload/main:resp:token_usage_record:response-" + (CALLS - 1));
            assertThat(payload.code()).isEqualTo(200);
            assertThat(payload.body().string()).contains("synthetic-answer-" + (CALLS - 1));
            var diagnostics = client.get(api + "/diagnostics");
            assertThat(diagnostics.code()).isEqualTo(200);
            var main = json.readTree(diagnostics.body().string()).at("/parity/agents/0");
            assertThat(main.path("llmCalls").asLong()).isEqualTo(CALLS);
            assertThat(main.at("/tokenSegments/total").asLong()).isEqualTo(CALLS * 11L);
          });
    }
  }

  private static void writeSource(Path root) throws Exception {
    Files.createDirectories(root);
    Files.writeString(
        root.resolve("session_index.jsonl"),
        "{\"id\":\""
            + SESSION_ID
            + "\",\"thread_name\":\"Synthetic"
            + " capacity\",\"updated_at\":\"2026-09-06T10:00:02Z\"}\n");
    Path transcript = root.resolve("sessions/2026/09/06/rollout-100-" + SESSION_ID + ".jsonl");
    Files.createDirectories(transcript.getParent());
    try (BufferedWriter output = Files.newBufferedWriter(transcript)) {
      output.write(
          "{\"type\":\"session_meta\",\"timestamp\":\"2026-09-06T10:00:00Z\",\"payload\":{\"id\":\""
              + SESSION_ID
              + "\",\"cwd\":\"/synthetic\"}}\n");
      output.write("{\"type\":\"turn_context\",\"payload\":{\"model\":\"synthetic-model\"}}\n");
      for (int index = 0; index < CALLS; index++) {
        output.write(
            "{\"type\":\"response_item\",\"timestamp\":\"2026-09-06T10:00:01Z\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"synthetic-question-"
                + index
                + "\"}]}}\n");
        output.write(
            "{\"type\":\"response_item\",\"timestamp\":\"2026-09-06T10:00:02Z\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"synthetic-answer-"
                + index
                + "\"}]}}\n");
        output.write(
            "{\"type\":\"token_usage_record\",\"timestamp\":\"2026-09-06T10:00:02Z\",\"payload\":{\"response_id\":\"response-"
                + index
                + "\",\"turn_id\":\"turn-"
                + index / CALLS_PER_ROUND
                + "\",\"usage\":{\"input_tokens\":10,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":1}}}\n");
      }
    }
  }
}
