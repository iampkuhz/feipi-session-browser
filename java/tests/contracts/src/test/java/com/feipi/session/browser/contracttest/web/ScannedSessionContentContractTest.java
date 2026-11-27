package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.contracttest.support.ContractTestComposition;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import com.feipi.session.browser.web.IndexSnapshotGuard;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.Javalin;
import io.javalin.testtools.TestCase;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 合成源经真实发现、扫描、磁盘制品重读后，列表与 round 仍保留内容。 */
class ScannedSessionContentContractTest {
  private static final String SESSION_ID = "11111111-1111-4111-8111-111111111111";
  private static final String PROMPT = "Synthetic scan content question";
  private static final String ANSWER = "Synthetic scan assistant answer";
  private static final ObjectMapper JSON = new ObjectMapper();

  @TempDir Path tempDir;

  @ParameterizedTest(name = "{0}: 扫描持久化后列表与 round 内容可读")
  @ValueSource(
      strings = {
        "claude_code",
        "codex",
        "qoder",
        "codex_event_only",
        "codex_event_usage",
        "codex_dual",
        "codex_multiturn",
        "codex_response_only"
      })
  void scannedContentSurvivesReopenAndHttp(String scenario) throws Exception {
    Path sourceRoot = tempDir.resolve("source");
    Files.createDirectories(sourceRoot);
    SourceAdapter adapter = writeSource(scenario, sourceRoot);
    String agent = adapter.sourceId().getValue();
    Path artifacts = tempDir.resolve("artifacts");
    String jdbcUrl = "jdbc:sqlite:" + tempDir.resolve("index.db").toAbsolutePath();
    try (var writer = DriverManager.getConnection(jdbcUrl)) {
      SqliteTestHelper.configureConnection(writer);
      var summary =
          new FullScanEngine()
              .scan(
                  SqliteTestHelper.createIndexWriter(writer),
                  ScanConfig.defaults(
                      List.of(new ScanConfig.SourceEntry(adapter, sourceRoot)), artifacts));
      assertThat(summary.errorCount()).as("scan issues: %s", summary.issues()).isZero();
      assertThat(summary.totalCandidates()).isEqualTo(1);
      assertThat(summary.successCount()).isEqualTo(1);
    }

    // 重开数据库并创建新的查询入口，不复用扫描内存对象。
    try (var index =
        IndexConnection.create(
            DriverManager.getConnection(jdbcUrl), PragmaConfig.DEFAULTS, jdbcUrl)) {
      try (var statement = index.writerConnection().createStatement();
          var rows =
              statement.executeQuery(
                  "SELECT s.agent, s.title, s.user_message_count, a.path FROM sessions s "
                      + "JOIN session_artifacts a ON a.session_key = s.session_key "
                      + "WHERE a.artifact_type = 'normalized'")) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getString("agent")).isEqualTo(agent);
        assertThat(rows.getString("title")).isEqualTo(PROMPT);
        if (scenario.equals("codex_dual")) {
          assertThat(rows.getLong("user_message_count")).isEqualTo(1);
        }
        Path artifact = Path.of(rows.getString("path"));
        assertThat(artifact).isRegularFile();
        assertThat(artifact.toAbsolutePath()).startsWith(artifacts.toAbsolutePath());
        assertThat(Files.readString(artifact)).contains(PROMPT, ANSWER);
        if (scenario.equals("codex_multiturn")) {
          assertThat(Files.readString(artifact)).contains(PROMPT + " second", ANSWER + " second");
        }
        assertThat(rows.next()).isFalse();
      }
      var web =
          new WebCompositionRoot(
              ContractTestComposition.queryRoot(index, new SchemaVersion(1)), WebConfig.defaults());
      withLoopbackServer(
          web.app(),
          (app, client) -> {
            var rowsResponse = client.get("/api/sessions/rows");
            assertThat(rowsResponse.code())
                .as(
                    "GET /api/sessions/rows: loopback port %s, snapshot header present: %s",
                    app.port(), rowsResponse.headers().get(IndexSnapshotGuard.HEADER) != null)
                .isEqualTo(200);
            var rows = JSON.readTree(rowsResponse.body().string()).path("rows");
            assertThat(rows.size()).isEqualTo(1);
            var row = rows.get(0);
            assertThat(row.path("title").asText()).isEqualTo(PROMPT);
            int expectedRounds = scenario.equals("codex_multiturn") ? 2 : 1;
            assertThat(row.path("rounds").asInt()).isEqualTo(expectedRounds);
            if (scenario.startsWith("codex_")) {
              assertThat(row.path("tokens").path("total").asLong())
                  .isEqualTo(
                      scenario.equals("codex_event_usage") || scenario.equals("codex_multiturn")
                          ? 15
                          : 0);
            }
            String api = "/api/sessions/" + agent + "/" + SESSION_ID + "/";
            for (String resource :
                List.of("meta", "metrics", "diagnostics", "rounds", "payloads")) {
              var response = client.get(api + resource);
              assertThat(response.code()).as(resource).isEqualTo(200);
              String body = response.body().string();
              assertThat(JSON.readTree(body).isObject()).as(resource).isTrue();
              if (resource.equals("rounds")) {
                assertThat(JSON.readTree(body).path("roundCount").asInt())
                    .isEqualTo(expectedRounds);
              }
              if (resource.equals("diagnostics")) {
                var agents = JSON.readTree(body).path("parity").path("agents");
                assertThat(agents.size()).isEqualTo(1);
                var main = agents.get(0);
                String freshPrecision =
                    switch (scenario) {
                      case "claude_code", "codex", "codex_event_usage" -> "provider_reported";
                      case "codex_multiturn" -> "mixed";
                      case "qoder" -> "estimated";
                      default -> "unknown";
                    };
                assertThat(main.at("/tokenSegments/provenance/freshInput").asText())
                    .as("逐调用来源经过磁盘重读及 HTTP，不借会话总标志：%s", scenario)
                    .isEqualTo(freshPrecision);
                if (scenario.equals("qoder")) {
                  assertThat(main.path("tokenUsageBasis").asText()).isEqualTo("session_estimate");
                } else {
                  assertThat(main.at("/tokenSegments/total").asLong())
                      .isEqualTo(
                          List.of("claude_code", "codex", "codex_event_usage", "codex_multiturn")
                                  .contains(scenario)
                              ? 15
                              : 0);
                  assertThat(main.path("tokenUsageBasis").asText())
                      .isEqualTo("artifact_call_usage");
                }
              }
              if (resource.equals("payloads") && expectedRounds == 2) {
                boolean secondRequestFound = false;
                for (var payload : JSON.readTree(body).path("payloads")) {
                  if (payload.path("kind").asText().equals("llm_request")) {
                    var originalRequest = client.get(payload.path("apiUrl").asText());
                    assertThat(originalRequest.code()).isEqualTo(200);
                    secondRequestFound |=
                        originalRequest.body().string().contains(PROMPT + " second");
                  }
                }
                assertThat(secondRequestFound).as("第二轮 Request payload 保留原用户正文").isTrue();
              }
            }
            var round = client.get(api + "round/1");
            assertThat(round.code()).isEqualTo(200);
            assertThat(round.body().string()).contains(ANSWER);
            if (expectedRounds == 2) {
              var second = client.get(api + "round/2");
              assertThat(second.code()).isEqualTo(200);
              assertThat(second.body().string()).contains(ANSWER + " second");
            }
            var detail = client.get("/sessions/" + agent + "/" + SESSION_ID);
            assertThat(detail.code()).isEqualTo(200);
            assertThat(detail.body().string()).contains("round");
          });
    }
  }

  private static void withLoopbackServer(Javalin app, TestCase check) throws Exception {
    // 每个扫描样例拥有独立的直连客户端，避免复用其他测试的连接或系统代理。
    try (var transport = HttpClient.newBuilder().proxy(ProxySelector.of(null)).build()) {
      app.start("127.0.0.1", 0);
      check.accept(app, new io.javalin.testtools.HttpClient(app, transport));
    } finally {
      app.stop();
    }
  }

  @Test
  void resultSourceAnchorsSurviveFreshScanAndReopen() throws Exception {
    Path sourceRoot = tempDir.resolve("anchor-source");
    write(
        sourceRoot.resolve("session_index.jsonl"),
        "{\"id\":\"" + SESSION_ID + "\",\"thread_name\":\"Synthetic anchors\"}\n");
    write(
        sourceRoot.resolve("sessions/2026/09/06/rollout-100-" + SESSION_ID + ".jsonl"),
        """
        {"type":"session_meta","payload":{"id":"%s","cwd":"/synthetic"}}
        {"type":"turn_context","payload":{"model":"synthetic-model"}}
        {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Synthetic anchors"}]}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"T","name":"exec_command","arguments":"synthetic input"}}
        {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"T","output":"same result"}}
        {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":2,"output_tokens":2,"total_tokens":4}}}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"T","output":"same result"}}
        {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":3,"output_tokens":3,"total_tokens":6}}}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"T","output":""}}
        """
            .formatted(SESSION_ID));
    Path artifacts = tempDir.resolve("anchor-artifacts");
    String jdbcUrl = "jdbc:sqlite:" + tempDir.resolve("anchor-index.db").toAbsolutePath();
    try (var writer = DriverManager.getConnection(jdbcUrl)) {
      SqliteTestHelper.configureConnection(writer);
      var summary =
          new FullScanEngine()
              .scan(
                  SqliteTestHelper.createIndexWriter(writer),
                  ScanConfig.defaults(
                      List.of(new ScanConfig.SourceEntry(new CodexSourceAdapter(), sourceRoot)),
                      artifacts));
      assertThat(summary.errorCount()).as("scan issues: %s", summary.issues()).isZero();
      assertThat(summary.totalCandidates()).isEqualTo(1);
      assertThat(summary.successCount()).isEqualTo(1);
    }
    // writer 已关闭；由新连接定位发布制品，再从磁盘游标重读，不复用 normalization 对象。
    try (var index =
            IndexConnection.create(
                DriverManager.getConnection(jdbcUrl), PragmaConfig.DEFAULTS, jdbcUrl);
        var statement = index.writerConnection().createStatement();
        var rows =
            statement.executeQuery(
                "SELECT path FROM session_artifacts WHERE artifact_type = 'normalized'")) {
      assertThat(rows.next()).isTrue();
      Path artifact = Path.of(rows.getString("path"));
      assertThat(artifact).isRegularFile();
      assertThat(artifact.toAbsolutePath()).startsWith(artifacts.toAbsolutePath());
      assertThat(rows.next()).isFalse();
      var calls = new ArrayList<NormalizedCall>();
      var tools = new ArrayList<NormalizedToolExecution>();
      var catalog = new LinkedHashMap<String, SourceUnitCatalogEntry>();
      try (var cursor = NormalizedArtifactLoader.open(artifact).openCursor()) {
        while (cursor.hasNext()) {
          var unit = cursor.next();
          calls.addAll(unit.calls());
          tools.addAll(unit.toolExecutions());
          unit.sourceUnitCatalog()
              .forEach((key, value) -> assertThat(catalog.putIfAbsent(key, value)).isNull());
        }
      }
      assertThat(calls).hasSize(3);
      assertThat(tools)
          .singleElement()
          .satisfies(
              tool -> {
                assertThat(tool.declaredByCallId()).isEqualTo(calls.getFirst().callId());
                assertThat(tool.resultConsumedByCallId()).isEmpty();
              });
      var results =
          catalog.values().stream()
              .filter(entry -> "tool_result".equals(entry.unitType()))
              .sorted(java.util.Comparator.comparingLong(SourceUnitCatalogEntry::eventOrder))
              .toList();
      assertThat(results).extracting(SourceUnitCatalogEntry::eventOrder).containsExactly(5, 7, 9);
      assertThat(results).extracting(SourceUnitCatalogEntry::unitKey).doesNotHaveDuplicates();
      assertThat(results)
          .extracting(entry -> entry.text().orElseThrow())
          .containsExactly("same result", "same result", "");
      assertThat(calls.getFirst().sourceUnits())
          .noneMatch(unit -> unit.containsKey("result_source_unit_key"));
      assertThat(calls.getFirst().request().toolResultIds()).isEmpty();
      for (var call : calls.subList(1, 3)) {
        long expectedEvent = call.callIndex() == 2 ? 5 : 7;
        var expected =
            results.stream()
                .filter(entry -> entry.eventOrder() == expectedEvent)
                .findFirst()
                .orElseThrow();
        assertThat(call.sourceUnits())
            .filteredOn(unit -> "tool_result".equals(unit.get("type")))
            .singleElement()
            .satisfies(
                unit ->
                    assertThat(unit).containsEntry("result_source_unit_key", expected.unitKey()));
        assertThat(call.request().toolResultIds()).containsExactly(tools.getFirst().toolCallId());
      }
      String tailKey =
          results.stream()
              .filter(entry -> entry.eventOrder() == 9)
              .findFirst()
              .orElseThrow()
              .unitKey();
      assertThat(calls.stream().flatMap(call -> call.sourceUnits().stream()))
          .noneMatch(unit -> tailKey.equals(unit.get("result_source_unit_key")));
      assertThat(calls)
          .allSatisfy(
              call -> {
                assertThat(call.usage().fresh()).isEqualTo(1);
                assertThat(call.usage().output()).isEqualTo(1);
              });
      assertLocalResultTargetsSurviveReopen(artifact, calls, tools.getFirst().toolCallId());
    }
  }

  private static void assertLocalResultTargetsSurviveReopen(
      Path artifact, List<NormalizedCall> calls, String toolId) throws Exception {
    var results =
        new SessionContentReader(NormalizedArtifactLoader.open(artifact), 1)
            .localResults("tool:result:" + toolId, PayloadVisibility.FULL);
    assertThat(results.coverage()).isEqualTo("complete");
    assertThat(results.nextCursor()).isNull();
    assertThat(results.occurrences())
        .hasSize(3)
        .allSatisfy(item -> assertThat(item.identity()).isEqualTo("confirmed"));
    assertThat(results.occurrences())
        .extracting(item -> item.content().text())
        .containsExactly("same result", "same result", "");
    assertThat(results.occurrences()).extracting(item -> item.order()).isSorted();
    assertThat(results.occurrences())
        .extracting(item -> item.occurrenceId())
        .doesNotHaveDuplicates();
    for (int index = 0; index < results.occurrences().size(); index++) {
      var occurrence = results.occurrences().get(index);
      // 每一步均从磁盘制品创建独立 reader，不依赖前一次投影对象保存随机句柄。
      var relations =
          new SessionContentReader(NormalizedArtifactLoader.open(artifact), 1)
              .localResultRelations(occurrence.occurrenceId(), 0, 20, null);
      assertThat(relations.coverage()).isEqualTo("complete");
      if (index == 2) {
        assertThat(relations.targets()).isEmpty();
      } else {
        assertThat(relations.targets()).hasSize(1);
        var target = relations.targets().getFirst();
        assertThat(target.callId()).isEqualTo(calls.get(index + 1).callId());
        var input =
            new SessionContentReader(NormalizedArtifactLoader.open(artifact), 1)
                .localResults(
                    target.requestPayloadId(), 0, 20, target.target(), PayloadVisibility.FULL);
        assertThat(input.references())
            .singleElement()
            .satisfies(
                reference -> {
                  assertThat(reference.referenceId()).isEqualTo(target.referenceId());
                  assertThat(reference.occurrenceId()).isEqualTo(occurrence.occurrenceId());
                  assertThat(reference.content()).isEqualTo(occurrence.content());
                });
      }
    }
  }

  static SourceAdapter writeSource(String agent, Path root) throws Exception {
    return switch (agent) {
      case "claude_code" -> {
        // Claude 从 history 驱动发现，必须同时提供索引条目和对应 transcript。
        write(
            root.resolve("history.jsonl"),
            """
            {"sessionId":"%s","project":"synthetic","display":"%s","timestamp":1788688800000}
            """
                .formatted(SESSION_ID, PROMPT));
        write(
            root.resolve("projects/synthetic/" + SESSION_ID + ".jsonl"),
            """
            {"type":"user","uuid":"u1","sessionId":"%s","timestamp":"2026-09-06T10:00:00Z","cwd":"/synthetic","message":{"role":"user","content":"%s"}}
            {"type":"assistant","uuid":"a1","sessionId":"%s","timestamp":"2026-09-06T10:00:01Z","message":{"id":"a1","role":"assistant","model":"synthetic-model","content":[{"type":"text","text":"%s"},{"type":"tool_use","id":"tool1","name":"Read","input":{"file_path":"synthetic.txt"}}],"usage":{"input_tokens":10,"output_tokens":5}}}
            {"type":"user","uuid":"t1","sessionId":"%s","timestamp":"2026-09-06T10:00:02Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"tool1","content":"Synthetic tool output"}]}}
            """
                .formatted(SESSION_ID, PROMPT, SESSION_ID, ANSWER, SESSION_ID));
        yield new ClaudeSourceAdapter();
      }
      case "codex",
          "codex_event_only",
          "codex_event_usage",
          "codex_dual",
          "codex_tools",
          "codex_multiturn",
          "codex_response_only" -> {
        write(
            root.resolve("session_index.jsonl"),
            "{\"id\":\""
                + SESSION_ID
                + "\",\"thread_name\":\""
                + PROMPT
                + "\",\"updated_at\":\"2026-09-06T10:00:02Z\"}\n");
        write(
            root.resolve("sessions/2026/09/06/rollout-100-" + SESSION_ID + ".jsonl"),
            agent.equals("codex")
                ? """
                {"type":"session_meta","timestamp":"2026-09-06T10:00:00Z","payload":{"id":"%s","cwd":"/synthetic"}}
                {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"%s"}]}}
                {"type":"response_item","timestamp":"2026-09-06T10:00:01Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"%s"}]}}
                {"type":"event_msg","timestamp":"2026-09-06T10:00:02Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15},"last_token_usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15}}}}
                """
                    .formatted(SESSION_ID, PROMPT, ANSWER)
                : codexEventTranscript(agent));
        yield new CodexSourceAdapter();
      }
      case "qoder" -> {
        write(
            root.resolve("projects/synthetic/" + SESSION_ID + ".jsonl"),
            """
            {"type":"user","role":"user","uuid":"u1","sessionId":"%s","timestamp":"2026-09-06T10:00:00Z","parts":[{"type":"text","text":"%s"}]}
            {"type":"assistant","role":"assistant","uuid":"a1","sessionId":"%s","timestamp":"2026-09-06T10:00:01Z","parts":[{"type":"text","text":"%s"}]}
            """
                .formatted(SESSION_ID, PROMPT, SESSION_ID, ANSWER));
        yield new QoderSourceAdapter();
      }
      default -> throw new IllegalArgumentException(agent);
    };
  }

  private static String codexEventTranscript(String scenario) {
    if (scenario.equals("codex_tools")) {
      return """
      {"type":"session_meta","timestamp":"2026-11-05T10:00:00Z","payload":{"id":"%s","cwd":"/synthetic"}}
      {"type":"turn_context","payload":{"model":"synthetic-model"}}
      {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"%s"}]}}
      {"type":"response_item","payload":{"type":"function_call","id":"item-a","call_id":"tool-a","name":"Read","arguments":{"file_path":"/synthetic/alpha.txt"}}}
      {"type":"response_item","payload":{"type":"function_call","id":"item-b","call_id":"tool-b","name":"Read","arguments":"{\\\"file_path\\\":\\\"/synthetic/beta.txt\\\"}"}}
      {"type":"response_item","payload":{"type":"function_call_output","call_id":"tool-b","output":"synthetic beta result"}}
      {"type":"response_item","payload":{"type":"function_call_output","call_id":"tool-a","output":"synthetic alpha result"}}
      {"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"%s"}]}}
      {"type":"event_msg","timestamp":"2026-11-05T10:00:09Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"cached_input_tokens":0,"cache_creation_input_tokens":0,"output_tokens":5,"total_tokens":15}}}}
      """
          .formatted(SESSION_ID, PROMPT, ANSWER);
    }
    if (scenario.equals("codex_response_only")) {
      return """
      {"type":"session_meta","timestamp":"2026-11-05T10:00:00Z","payload":{"id":"%s","cwd":"/synthetic"}}
      {"type":"response_item","timestamp":"2026-11-05T10:00:01Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"%s"}]}}
      {"type":"response_item","timestamp":"2026-11-05T10:00:02Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"%s"}]}}
      """
          .formatted(SESSION_ID, PROMPT, ANSWER);
    }
    String events =
        """
        {"type":"session_meta","timestamp":"2026-11-05T10:00:00Z","payload":{"id":"%s","cwd":"/synthetic"}}
        {"type":"turn_context","timestamp":"2026-11-05T10:00:00Z","payload":{"model":"synthetic-model"}}
        {"type":"event_msg","timestamp":"2026-11-05T10:00:01Z","payload":{"type":"user_message","message":"%s"}}
        {"type":"event_msg","timestamp":"2026-11-05T10:00:02Z","payload":{"type":"agent_message","message":"%s"}}
        """
            .formatted(SESSION_ID, PROMPT, ANSWER);
    String tail =
        scenario.equals("codex_multiturn")
            ? """
            {"type":"event_msg","timestamp":"2026-11-05T10:00:04Z","payload":{"type":"user_message","message":"%s second"}}
            {"type":"event_msg","timestamp":"2026-11-05T10:00:05Z","payload":{"type":"agent_message","message":"%s second"}}
            """
                .formatted(PROMPT, ANSWER)
            : "";
    return events
        + switch (scenario) {
          case "codex_event_usage", "codex_multiturn" ->
              """
              {"type":"event_msg","timestamp":"2026-11-05T10:00:03Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15}}}}
              """;
          case "codex_dual" ->
              """
              {"type":"response_item","timestamp":"2026-11-05T10:00:01Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"%s"}]}}
              {"type":"response_item","timestamp":"2026-11-05T10:00:02Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"%s"}]}}
              """
                  .formatted(PROMPT, ANSWER);
          default -> "";
        }
        + tail;
  }

  private static void write(Path path, String content) throws Exception {
    Files.createDirectories(path.getParent());
    Files.writeString(path, content);
  }
}
