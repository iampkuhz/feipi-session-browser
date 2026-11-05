package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.contracttest.support.ContractTestComposition;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.List;
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
  @ValueSource(strings = {"claude_code", "codex", "qoder"})
  void scannedContentSurvivesReopenAndHttp(String agent) throws Exception {
    Path sourceRoot = tempDir.resolve("source");
    Files.createDirectories(sourceRoot);
    SourceAdapter adapter = writeSource(agent, sourceRoot);
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
                  "SELECT s.agent, s.title, a.path FROM sessions s "
                      + "JOIN session_artifacts a ON a.session_key = s.session_key "
                      + "WHERE a.artifact_type = 'normalized'")) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getString("agent")).isEqualTo(agent);
        assertThat(rows.getString("title")).isEqualTo(PROMPT);
        Path artifact = Path.of(rows.getString("path"));
        assertThat(artifact).isRegularFile();
        assertThat(artifact.toAbsolutePath()).startsWith(artifacts.toAbsolutePath());
        assertThat(Files.readString(artifact)).contains(ANSWER);
        assertThat(rows.next()).isFalse();
      }
      var web =
          new WebCompositionRoot(
              ContractTestComposition.queryRoot(index, new SchemaVersion(1)), WebConfig.defaults());
      JavalinTest.test(
          web.app(),
          (app, client) -> {
            var rowsResponse = client.get("/api/sessions/rows");
            assertThat(rowsResponse.code()).isEqualTo(200);
            var rows = JSON.readTree(rowsResponse.body().string()).path("rows");
            assertThat(rows.size()).isEqualTo(1);
            var row = rows.get(0);
            assertThat(row.path("title").asText()).isEqualTo(PROMPT);
            assertThat(row.path("rounds").asInt()).isEqualTo(1);
            String api = "/api/sessions/" + agent + "/" + SESSION_ID + "/";
            for (String resource :
                List.of("meta", "metrics", "diagnostics", "rounds", "payloads")) {
              var response = client.get(api + resource);
              assertThat(response.code()).as(resource).isEqualTo(200);
              String body = response.body().string();
              assertThat(JSON.readTree(body).isObject()).as(resource).isTrue();
              if (resource.equals("rounds")) {
                assertThat(JSON.readTree(body).path("roundCount").asInt()).isEqualTo(1);
              }
            }
            var round = client.get(api + "round/1");
            assertThat(round.code()).isEqualTo(200);
            assertThat(round.body().string()).contains(ANSWER);
            var detail = client.get("/sessions/" + agent + "/" + SESSION_ID);
            assertThat(detail.code()).isEqualTo(200);
            assertThat(detail.body().string()).contains("round");
          });
    }
  }

  private static SourceAdapter writeSource(String agent, Path root) throws Exception {
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
      case "codex" -> {
        write(
            root.resolve("session_index.jsonl"),
            "{\"id\":\""
                + SESSION_ID
                + "\",\"thread_name\":\""
                + PROMPT
                + "\",\"updated_at\":\"2026-09-06T10:00:02Z\"}\n");
        write(
            root.resolve("sessions/2026/09/06/rollout-100-" + SESSION_ID + ".jsonl"),
            """
            {"type":"session_meta","timestamp":"2026-09-06T10:00:00Z","payload":{"id":"%s","cwd":"/synthetic"}}
            {"type":"response_item","timestamp":"2026-09-06T10:00:00Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"%s"}]}}
            {"type":"response_item","timestamp":"2026-09-06T10:00:01Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"%s"}]}}
            {"type":"event_msg","timestamp":"2026-09-06T10:00:02Z","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15},"last_token_usage":{"input_tokens":10,"output_tokens":5,"total_tokens":15}}}}
            """
                .formatted(SESSION_ID, PROMPT, ANSWER));
        yield new CodexSourceAdapter();
      }
      case "qoder" -> {
        write(
            root.resolve("projects/synthetic/" + SESSION_ID + ".jsonl"),
            """
            {"type":"message","role":"user","uuid":"u1","sessionId":"%s","timestamp":"2026-09-06T10:00:00Z","parts":[{"type":"text","text":"%s"}]}
            {"type":"message","role":"assistant","uuid":"a1","sessionId":"%s","timestamp":"2026-09-06T10:00:01Z","parts":[{"type":"text","text":"%s"}]}
            """
                .formatted(SESSION_ID, PROMPT, SESSION_ID, ANSWER));
        yield new QoderSourceAdapter();
      }
      default -> throw new IllegalArgumentException(agent);
    };
  }

  private static void write(Path path, String content) throws Exception {
    Files.createDirectories(path.getParent());
    Files.writeString(path, content);
  }
}
