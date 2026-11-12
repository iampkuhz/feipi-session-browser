package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.contracttest.support.ContractTestComposition;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.scan.artifact.CanonicalJsonWriter;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import com.feipi.session.browser.web.api.SessionApiHandler;
import com.feipi.session.browser.web.api.SessionApiService;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 合成真实来源经 spool、双归一化、磁盘内容重读及两种 HTTP 投影保真。 */
class CodexToolObservationContractTest {
  private static final String ID = "11111111-1111-4111-8111-111111111111";
  private static final ObjectMapper JSON = new ObjectMapper();
  @TempDir Path directory;

  @Test
  void existingSyntheticToolLoopRetainsExplicitEndWithoutChangingTaskTimingOrCounts()
      throws Exception {
    Path fixture =
        Path.of(
            System.getProperty("repo.root.dir"),
            "java/tests/fixtures/normalized/codex/tool_loop.input/rollout.jsonl");
    String source = Files.readString(fixture);
    var artifacts =
        new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact>();
    for (boolean includeEnd : List.of(false, true)) {
      Path file = directory.resolve("fixture.jsonl");
      Files.writeString(
          file,
          includeEnd
              ? source
              : source
                  .lines()
                  .filter(line -> !line.contains("exec_command_end"))
                  .collect(java.util.stream.Collectors.joining("\n")));
      var adapter = new CodexSourceAdapter();
      try (var parsed =
          (SourceResult.Success)
              adapter.parse(
                  new Candidate(adapter.fingerprint(file), "synthetic", "", Map.of()), null)) {
        artifacts.add(
            new NormalizationEngine()
                .normalize(NormalizedAgent.CODEX, parsed.records(), List.of(), List.of()));
      }
    }
    var without = artifacts.get(0);
    var with = artifacts.get(1);
    assertThat(with.toolExecutions()).hasSize(1);
    var tool = with.toolExecutions().getFirst();
    assertThat(tool.durationMs()).isEqualTo(2000L);
    assertThat(tool.exitCode()).contains(0);
    assertThat(tool.observation().orElseThrow().durationNanos()).isEqualTo(2_000_000_000L);
    assertThat(without.toolExecutions().getFirst().durationMs()).isNull();
    assertThat(with.session().get("timing")).isEqualTo(without.session().get("timing"));
    assertThat(with.session().get("totalTokens")).isEqualTo(without.session().get("totalTokens"));
    assertThat(with.calls()).hasSameSizeAs(without.calls());
    assertThat(with.toolExecutions()).hasSameSizeAs(without.toolExecutions());
    assertThat(with.session().get("consumedResults"))
        .isEqualTo(without.session().get("consumedResults"));
  }

  @ParameterizedTest
  @ValueSource(booleans = {false, true})
  void sourceToBothHttpPathsPreservesUnknownZeroAndProvenance(boolean spooled) throws Exception {
    Path root = directory.resolve("source");
    var adapter = ScannedSessionContentContractTest.writeSource("codex_tools", root);
    Path file = root.resolve("sessions/2026/09/06/rollout-100-" + ID + ".jsonl");
    String source = Files.readString(file);
    String positive = end("tool-a", "{\"secs\":2,\"nanos\":1}", 0, "completed");
    String zero = end("tool-b", "{\"secs\":0,\"nanos\":0}", 7, "failed");
    int firstLine = source.indexOf('\n') + 1;
    source =
        source.substring(0, firstLine) + positive + source.substring(firstLine) + positive + zero;
    source +=
        """
        {"type":"response_item","payload":{"type":"function_call","call_id":"tool-c","name":"Read","arguments":"{}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"tool-c","output":"Wall time: 99 seconds; Process exited with code 0"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"tool-d","name":"Read","arguments":"{}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"tool-d","output":"synthetic invalid measurement"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"tool-e","name":"Read","arguments":"{}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"tool-e","output":"synthetic conflicting measurement"}}
        {"type":"response_item","payload":{"type":"message","role":"assistant","content":"%s"}}
        """
            .formatted(spooled ? "synthetic ".repeat(120_000) : "synthetic final");
    source +=
        end("tool-d", "{\"secs\":-1,\"nanos\":0}", 0, "completed")
            + end("tool-e", "{\"secs\":0,\"nanos\":0}", 0, "completed")
            + end("tool-e", "{\"secs\":1,\"nanos\":0}", 0, "completed");
    Files.writeString(file, source);
    var codex = (CodexSourceAdapter) adapter;
    try (var parsed =
        (SourceResult.Success)
            codex.parse(new Candidate(codex.fingerprint(file), "synthetic", "", Map.of()), null)) {
      assertThat(parsed.hasManagedRecords()).isEqualTo(spooled);
      var records = new ArrayList<SourceRecord>();
      try (var cursor = parsed.recordSequence().openCursor()) {
        while (cursor.hasNext()) records.add(cursor.next());
      }
      var engine = new NormalizationEngine();
      var ordinary = engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
      var managed =
          engine.normalizeContent(
              NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), List.of());
      assertThat(managed.toArtifact()).isEqualTo(ordinary);
      assertThat(ordinary.toolExecutions()).hasSize(5);
      assertThat(ordinary.calls()).hasSize(1);
      assertThat(ordinary.calls().getFirst().request().toolResultIds())
          .containsExactly("tool-b", "tool-a");
      assertThat(ordinary.toolExecutions().subList(2, 5))
          .allSatisfy(tool -> assertThat(tool.resultConsumedByCallId()).isEmpty());
      assertThat(ordinary.sourceUnitCatalog()).hasSize(5);
      assertThat(ordinary.calls().stream().mapToLong(call -> call.usage().total()).sum())
          .isEqualTo(15);
      Path canonical = directory.resolve("canonical.json");
      Files.write(canonical, new CanonicalJsonWriter().serialize(ordinary));
      var reloaded = NormalizedArtifactLoader.load(canonical);
      assertThat(reloaded.toolExecutions()).isEqualTo(ordinary.toolExecutions());
      assertThat(reloaded.calls()).isEqualTo(ordinary.calls());
    }

    String jdbc = "jdbc:sqlite:" + directory.resolve("index.db");
    try (var writer = DriverManager.getConnection(jdbc)) {
      SqliteTestHelper.configureConnection(writer);
      var result =
          new FullScanEngine()
              .scan(
                  SqliteTestHelper.createIndexWriter(writer),
                  ScanConfig.defaults(
                      List.of(new ScanConfig.SourceEntry(adapter, root)),
                      directory.resolve("artifacts")));
      assertThat(result.errorCount()).as("%s", result.issues()).isZero();
      assertThat(result.successCount()).isEqualTo(1);
    }
    try (var index =
        IndexConnection.create(DriverManager.getConnection(jdbc), PragmaConfig.DEFAULTS, jdbc)) {
      var query = ContractTestComposition.queryRoot(index, new SchemaVersion(1));
      var context =
          query
              .sessionDetail()
              .getDetailContext("codex:" + ID, PayloadVisibility.STANDARD)
              .orElseThrow();
      var artifact = context.content().toArtifact();
      var detail =
          new SessionDetail(
              context.detail().sessionRow(),
              SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()),
              List.of(),
              PayloadVisibility.STANDARD,
              "",
              "",
              "synthetic");
      var materialized = new SessionDetailUseCase.DetailContext(detail, artifact);
      var content =
          new SessionDetailUseCase.DetailContext(context.detail(), null, context.content());
      var first =
          new SessionApiHandler(
              new SessionApiService((key, visibility) -> Optional.of(materialized)));
      var second =
          new SessionApiHandler(new SessionApiService((key, visibility) -> Optional.of(content)));
      JavalinTest.test(
          Javalin.create(
              config -> {
                config.routes.get("/artifact", ctx -> first.handleRound(ctx, "codex", ID, 1));
                config.routes.get("/content", ctx -> second.handleRound(ctx, "codex", ID, 1));
              }),
          (app, client) -> {
            for (String path : List.of("/artifact", "/content", "/artifact?limit=100")) {
              var response = client.get(path);
              assertThat(response.code()).isEqualTo(200);
              var tools = JSON.readTree(response.body().string()).at("/round/tools");
              assertThat(tools.size()).isEqualTo(5);
              assertTool(tools, "tool-a", 2000L, 2_000_000_001L, 0, "completed");
              assertTool(tools, "tool-b", 0L, 0L, 7, "failed");
              var unknown = find(tools, "tool-c");
              assertThat(unknown.path("durationMs").isNull()).isTrue();
              assertThat(unknown.path("observation").isNull()).isTrue();
              var invalid = find(tools, "tool-d");
              assertThat(invalid.path("durationMs").isNull()).isTrue();
              assertThat(invalid.at("/observation/issue").asText()).isEqualTo("invalid_duration");
              var conflict = find(tools, "tool-e");
              assertThat(conflict.path("durationMs").isNull()).isTrue();
              assertThat(conflict.path("exitCode").isNull()).isTrue();
              assertThat(conflict.at("/observation/issue").asText())
                  .isEqualTo("conflicting_observations");
            }
          });
    }
  }

  @ParameterizedTest
  @ValueSource(booleans = {false, true})
  void tailPresenceSurvivesActualSpoolCanonicalIndexReopenAndAllDownloads(boolean spooled)
      throws Exception {
    Path root = directory.resolve("source");
    var adapter =
        (CodexSourceAdapter) ScannedSessionContentContractTest.writeSource("codex_tools", root);
    Path file = root.resolve("sessions/2026/09/06/rollout-100-" + ID + ".jsonl");
    String source = Files.readString(file);
    if (spooled)
      source = source.replace("Synthetic scan assistant answer", "synthetic ".repeat(120_000));
    source +=
        """
        {"type":"response_item","payload":{"type":"function_call","call_id":"tail","name":"Read","arguments":"{}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"tail","output":"synthetic eof result"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"empty","name":"Read","arguments":"{}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"empty","output":""}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"missing","name":"Read","arguments":"{}"}}
        """
            + end("missing", "{\"secs\":0,\"nanos\":0}", 0, "completed");
    Files.writeString(file, source);
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(file), "synthetic", "", Map.of()), null)) {
      assertThat(parsed.hasManagedRecords()).isEqualTo(spooled);
    }
    String jdbc = "jdbc:sqlite:" + directory.resolve("fresh.db");
    try (var writer = DriverManager.getConnection(jdbc)) {
      SqliteTestHelper.configureConnection(writer);
      var scan =
          new FullScanEngine()
              .scan(
                  SqliteTestHelper.createIndexWriter(writer),
                  ScanConfig.defaults(
                      List.of(new ScanConfig.SourceEntry(adapter, root)),
                      directory.resolve("artifacts")));
      assertThat(scan.errorCount()).as("%s", scan.issues()).isZero();
      assertThat(scan.successCount()).isEqualTo(1);
    }
    try (var index =
        IndexConnection.create(DriverManager.getConnection(jdbc), PragmaConfig.DEFAULTS, jdbc)) {
      var query = ContractTestComposition.queryRoot(index, new SchemaVersion(1));
      var context =
          query
              .sessionDetail()
              .getDetailContext("codex:" + ID, PayloadVisibility.STANDARD)
              .orElseThrow();
      assertThat(context.artifact() == null).isEqualTo(spooled);
      var artifact = context.content().toArtifact();
      assertThat(artifact.calls()).hasSize(1);
      assertThat(artifact.toolExecutions()).hasSize(5);
      assertThat(artifact.calls().getFirst().request().toolResultIds())
          .containsExactly("tool-b", "tool-a");
      assertThat(artifact.toolExecutions().subList(2, 5))
          .allSatisfy(tool -> assertThat(tool.resultConsumedByCallId()).isEmpty());
      assertThat(
              artifact.sourceUnitCatalog().values().stream()
                  .filter(entry -> entry.unitType().equals("tool_result")))
          .hasSize(4);
      Path canonical = directory.resolve("reopened-canonical.json");
      Files.write(canonical, new CanonicalJsonWriter().serialize(artifact));
      assertThat(NormalizedArtifactLoader.load(canonical).sourceUnitCatalog())
          .isEqualTo(artifact.sourceUnitCatalog());
      var web =
          new com.feipi.session.browser.web.WebCompositionRoot(
              query, com.feipi.session.browser.web.WebConfig.defaults());
      JavalinTest.test(
          web.app(),
          (app, client) -> {
            String api = "/api/sessions/codex/" + ID + "/";
            for (String id : List.of("tail", "empty", "missing")) {
              var response = client.get(api + "payload/tool:result:" + id);
              assertThat(response.code()).isEqualTo(200);
              var body = JSON.readTree(response.body().string());
              assertThat(body.path("status").asText())
                  .isEqualTo(id.equals("missing") ? "missing" : "available");
              assertThat(body.path("content").asText())
                  .isEqualTo(id.equals("tail") ? "synthetic eof result" : "");
            }
            for (String path : List.of("round/1", "execution?limit=100")) {
              var response = client.get(api + path);
              assertThat(response.code()).isEqualTo(200);
              var body = JSON.readTree(response.body().string());
              var tools = path.startsWith("round") ? body.at("/round/tools") : body.path("items");
              for (var value : tools) {
                var tool = path.startsWith("round") ? value : value.path("tool");
                String id = tool.path("toolCallId").asText();
                if (List.of("tail", "empty", "missing").contains(id)) {
                  assertThat(tool.path("resultObserved").asBoolean())
                      .as(id)
                      .isEqualTo(!id.equals("missing"));
                }
              }
            }
            for (String path :
                List.of(
                    "/sessions/codex/" + ID + "/export.html",
                    "/export/html?agent=codex&session_id=" + ID,
                    "/export/mhtml?agent=codex&session_id=" + ID)) {
              var response = client.get(path);
              assertThat(response.code()).isEqualTo(200);
              String body = response.body().string();
              assertThat(body)
                  .contains("synthetic eof result", "Tool tail", "Tool empty", "Tool missing");
              assertThat(body).doesNotContain("fetch(", "<script");
            }
          });
    }
  }

  private static void assertTool(
      JsonNode tools, String id, long ms, long nanos, int exit, String status) {
    var tool = find(tools, id);
    assertThat(tool.path("durationMs").asLong()).isEqualTo(ms);
    assertThat(tool.path("exitCode").asInt()).isEqualTo(exit);
    assertThat(tool.at("/observation/durationNanos").asLong()).isEqualTo(nanos);
    assertThat(tool.at("/observation/kind").asText()).isEqualTo("executor_reported");
    assertThat(tool.at("/observation/status").asText()).isEqualTo(status);
    assertThat(tool.at("/observation/source").asText()).startsWith("codex:exec_command_end#event[");
    assertThat(tool.path("status").asText()).isEmpty();
  }

  private static JsonNode find(JsonNode tools, String id) {
    for (var tool : tools) if (tool.path("toolCallId").asText().equals(id)) return tool;
    throw new AssertionError("缺少工具 " + id);
  }

  private static String end(String id, String duration, int exit, String status) {
    return """
        {"timestamp":"2099-01-01T00:00:00Z","type":"event_msg","payload":{"type":"exec_command_end","call_id":"%s","process_id":"123","duration":%s,"exit_code":%d,"status":"%s"}}
        """
        .formatted(id, duration, exit, status);
  }
}
