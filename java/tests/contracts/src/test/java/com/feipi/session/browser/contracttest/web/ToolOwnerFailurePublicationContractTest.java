package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.IncrementalScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.ScanSummary;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 未完成工具段必须让真实扫描失败并保留旧发布，补齐助手后可正常重试。 */
class ToolOwnerFailurePublicationContractTest {
  private static final String SESSION_ID = "33333333-3333-4333-8333-333333333333";
  @TempDir Path tempDir;

  @ParameterizedTest
  @ValueSource(booleans = {false, true})
  void unfinishedToolSegmentRetainsPublicationAndRetryRecovers(boolean incremental)
      throws Exception {
    Path source = tempDir.resolve("source");
    Path raw = source.resolve("sessions/2026/09/06/rollout-100-" + SESSION_ID + ".jsonl");
    Files.createDirectories(raw.getParent());
    Files.writeString(
        source.resolve("session_index.jsonl"),
        "{\"id\":\""
            + SESSION_ID
            + "\",\"thread_name\":\"synthetic-question-1\","
            + "\"updated_at\":\"2026-09-06T10:00:02Z\"}\n");
    Files.writeString(
        raw,
        "{\"type\":\"session_meta\",\"timestamp\":\"2026-09-06T10:00:00Z\","
            + "\"payload\":{\"id\":\""
            + SESSION_ID
            + "\",\"cwd\":\"/synthetic\"}}\n"
            + unfinishedSegment(1)
            + assistant(1));
    var config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new CodexSourceAdapter(), source)),
            tempDir.resolve("artifacts"));
    try (var connection =
        DriverManager.getConnection("jdbc:sqlite:" + tempDir.resolve("index.db"))) {
      SqliteTestHelper.configureConnection(connection);
      assertSuccessful(scan(connection, config, incremental));
      var priorRows = rows(connection, "SELECT * FROM sessions ORDER BY session_key");
      var priorArtifacts =
          rows(connection, "SELECT * FROM session_artifacts ORDER BY session_key, artifact_type");
      var priorMetadata = rows(connection, "SELECT * FROM index_metadata ORDER BY key");
      String generation =
          scalar(connection, "SELECT value FROM index_metadata WHERE key='published_generation'");
      assertThat(generation).isNotBlank();
      assertThat(
              scalar(connection, "SELECT value FROM index_metadata WHERE key='scan_logic_version'"))
          .isEqualTo(Integer.toString(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION));
      Path oldArtifact =
          Path.of(
              scalar(
                  connection,
                  "SELECT path FROM session_artifacts WHERE artifact_type='normalized'"));
      byte[] oldBytes = Files.readAllBytes(oldArtifact);

      Files.writeString(raw, unfinishedSegment(2), StandardOpenOption.APPEND);
      var failed = scan(connection, config, incremental);
      assertThat(failed.totalCandidates()).isEqualTo(1);
      assertThat(failed.successCount()).isZero();
      assertThat(failed.errorCount()).isEqualTo(1);
      assertThat(failed.isFullySuccessful()).isFalse();
      assertThat(failed.issues())
          .anySatisfy(
              issue -> {
                assertThat(issue.sourceValue()).isEqualTo("codex");
                assertThat(issue.sessionKey()).contains(SESSION_ID);
                assertThat(issue.message()).contains("TOOL_OWNER_UNAVAILABLE");
              });
      assertThat(rows(connection, "SELECT * FROM sessions ORDER BY session_key"))
          .isEqualTo(priorRows);
      assertThat(
              rows(
                  connection,
                  "SELECT * FROM session_artifacts ORDER BY session_key, artifact_type"))
          .isEqualTo(priorArtifacts);
      assertThat(rows(connection, "SELECT * FROM index_metadata ORDER BY key"))
          .isEqualTo(priorMetadata);
      assertThat(Files.readAllBytes(oldArtifact)).isEqualTo(oldBytes);
      assertThat(scalar(connection, "SELECT status FROM scan_log WHERE id=" + failed.scanLogId()))
          .isEqualTo("failure");
      assertThat(
              scalar(connection, "SELECT error_count FROM scan_log WHERE id=" + failed.scanLogId()))
          .isEqualTo(Integer.toString(failed.errorCount()));
      assertThat(
              scalar(
                  connection, "SELECT failures_json FROM scan_log WHERE id=" + failed.scanLogId()))
          .contains("codex", SESSION_ID, "phase", "code", "TOOL_OWNER_UNAVAILABLE");

      Files.writeString(raw, assistant(2), StandardOpenOption.APPEND);
      var recovered = scan(connection, config, incremental);
      assertSuccessful(recovered);
      assertThat(
              scalar(connection, "SELECT status FROM scan_log WHERE id=" + recovered.scanLogId()))
          .isEqualTo("success");
      assertThat(
              scalar(
                  connection, "SELECT value FROM index_metadata WHERE key='published_generation'"))
          .isNotEqualTo(generation);
      assertThat(scalar(connection, "SELECT round_count FROM sessions")).isEqualTo("2");
      Path artifact =
          Path.of(
              scalar(
                  connection,
                  "SELECT path FROM session_artifacts WHERE artifact_type='normalized'"));
      var calls = new ArrayList<NormalizedCall>();
      var tools = new ArrayList<NormalizedToolExecution>();
      try (var cursor = NormalizedArtifactLoader.open(artifact).openCursor()) {
        while (cursor.hasNext()) {
          var unit = cursor.next();
          calls.addAll(unit.calls());
          tools.addAll(unit.toolExecutions());
        }
      }
      assertThat(calls).hasSize(2);
      assertThat(tools).hasSize(2);
      for (int number = 1; number <= 2; number++) {
        int segment = number;
        var call = calls.get(number - 1);
        assertThat(call.sourceUnits().stream().map(unit -> unit.get("text")))
            .contains("synthetic-question-" + number, "synthetic-answer-" + number);
        assertThat(tools)
            .filteredOn(tool -> tool.toolCallId().equals("tool-" + segment))
            .singleElement()
            .satisfies(
                tool -> {
                  assertThat(tool.declaredByCallId()).isEqualTo(call.callId());
                  assertThat(tool.resultConsumedByCallId()).contains(call.callId());
                });
      }
    }
  }

  private static ScanSummary scan(Connection connection, ScanConfig config, boolean incremental) {
    var writer = SqliteTestHelper.createIndexWriter(connection);
    if (!incremental) return new FullScanEngine().scan(writer, config);
    var result = new IncrementalScanEngine().scan(writer, config);
    return new ScanSummary(
        result.totalCandidates(),
        result.successCount(),
        result.skippedCount(),
        result.errorCount(),
        result.scanDurationMs(),
        result.scanLogId(),
        result.perSourceCount(),
        result.issues());
  }

  private static void assertSuccessful(ScanSummary summary) {
    assertThat(summary.errorCount()).as("scan issues: %s", summary.issues()).isZero();
    assertThat(summary.successCount()).isEqualTo(1);
    assertThat(summary.isFullySuccessful()).isTrue();
  }

  private static List<List<String>> rows(Connection connection, String sql) throws Exception {
    var result = new ArrayList<List<String>>();
    try (var statement = connection.createStatement();
        var rows = statement.executeQuery(sql)) {
      while (rows.next()) {
        var row = new ArrayList<String>();
        for (int column = 1; column <= rows.getMetaData().getColumnCount(); column++) {
          row.add(rows.getString(column));
        }
        result.add(row);
      }
    }
    return result;
  }

  private static String scalar(Connection connection, String sql) throws Exception {
    var values = rows(connection, sql);
    assertThat(values).hasSize(1);
    return values.getFirst().getFirst();
  }

  private static String unfinishedSegment(int number) {
    return """
    {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"synthetic-question-%1$d"}]}}
    {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"function_call","call_id":"tool-%1$d","name":"read_file","arguments":"{}"}}
    {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"function_call_output","call_id":"tool-%1$d","output":"synthetic-result-%1$d"}}
    """
        .formatted(number);
  }

  private static String assistant(int number) {
    return """
    {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"synthetic-answer-%d"}]}}
    """
        .formatted(number);
  }
}
