package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.contracttest.support.ContractTestComposition;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
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

/** 同一个合成 JSONL 经真实发现/扫描/磁盘重读与独立导入，验证事实和公开消费者。 */
class JsonlScanImportParityTest {
  private static final String SESSION = "11111111-1111-4111-8111-111111111111";
  private static final ObjectMapper JSON = new ObjectMapper();
  @TempDir Path directory;

  @ParameterizedTest
  @ValueSource(
      strings = {
        "claude_code",
        "codex",
        "codex_dual",
        "codex_tools",
        "qoder",
        "qoder_wrapped",
        "claude_code_pending",
        "codex_pending",
        "qoder_pending"
      })
  void sameFileRetainsFactsAndReadablePayloadAcrossEntrypoints(String scenario) throws Exception {
    boolean pending = scenario.endsWith("_pending");
    String agent =
        scenario.startsWith("codex_")
            ? "codex"
            : scenario.replace("_pending", "").replace("_wrapped", "");
    Path root = directory.resolve("source");
    var adapter =
        ScannedSessionContentContractTest.writeSource(
            scenario.startsWith("codex_") && !pending ? scenario : agent, root);
    var candidate = adapter.discover(root).orderedItems().getFirst();
    Path sourceFile = Path.of(candidate.fingerprint().locator());
    String transcript = Files.readString(sourceFile);
    if (agent.equals("qoder") && (pending || scenario.endsWith("_wrapped"))) {
      transcript =
          transcript
              .replace("\"type\":\"user\"", "\"type\":\"message\"")
              .replace("\"type\":\"assistant\"", "\"type\":\"message\"");
    }
    if (pending) {
      transcript =
          String.join("\n", transcript.lines().limit(agent.equals("codex") ? 2 : 1).toList());
    } else if (!agent.equals("codex")) {
      transcript =
          "{\"type\":\"runtime-config\",\"content\":\"synthetic ignored config\"}\n" + transcript;
    }
    Files.writeString(sourceFile, transcript);
    var source = NormalizedAgent.fromValue(agent);
    try (var imports = new IsolatedSessionImportService(ignored -> adapter)) {
      var imported = imports.create(Files.newInputStream(sourceFile), "synthetic.jsonl", source);
      String url = "jdbc:sqlite:" + directory.resolve("index.db");
      try (var writer = DriverManager.getConnection(url)) {
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
          IndexConnection.create(DriverManager.getConnection(url), PragmaConfig.DEFAULTS, url)) {
        try (var statement = index.writerConnection().createStatement();
            var rows =
                statement.executeQuery(
                    "SELECT s.user_message_count, s.total_tokens, a.path FROM sessions s JOIN session_artifacts a ON s.session_key=a.session_key WHERE a.artifact_type='normalized'")) {
          assertThat(rows.next()).isTrue();
          assertThat(rows.getLong("user_message_count"))
              .isEqualTo(imported.sessionRow().userMessageCount());
          assertThat(rows.getLong("user_message_count")).isEqualTo(1);
          assertThat(rows.getLong("total_tokens")).isEqualTo(imported.sessionRow().totalTokens());
          if (scenario.equals("qoder_wrapped")) {
            assertThat(rows.getLong("total_tokens")).isZero();
          }
          var scanned = NormalizedArtifactLoader.open(Path.of(rows.getString("path")));
          var compact = scanned.toArtifact();
          assertThat(compact.calls()).hasSameSizeAs(imported.artifact().calls());
          assertThat(compact.calls().stream().map(call -> call.usage()).toList())
              .containsExactlyElementsOf(
                  imported.artifact().calls().stream().map(call -> call.usage()).toList());
          assertThat(
                  compact.toolExecutions().stream()
                      .map(
                          tool ->
                              List.of(
                                  tool.toolCallId(),
                                  tool.name(),
                                  tool.scope(),
                                  tool.declaredByCallId(),
                                  tool.resultConsumedByCallId()))
                      .toList())
              .containsExactlyInAnyOrderElementsOf(
                  imported.artifact().toolExecutions().stream()
                      .map(
                          tool ->
                              List.of(
                                  tool.toolCallId(),
                                  tool.name(),
                                  tool.scope(),
                                  tool.declaredByCallId(),
                                  tool.resultConsumedByCallId()))
                      .toList());
          var scanReader =
              new SessionContentReader(scanned, imported.sessionRow().userMessageCount());
          var importReader =
              new SessionContentReader(
                  NormalizedSessionContent.fromArtifact(imported.artifact()),
                  imported.sessionRow().userMessageCount());
          for (var reader : List.of(scanReader, importReader)) {
            var payload = reader.payload("round:req:1", PayloadVisibility.STANDARD).orElseThrow();
            assertThat(payload.content()).contains("Synthetic scan content question");
            if (scenario.equals("codex_dual")) {
              assertThat(payload.content()).containsOnlyOnce("Synthetic scan content question");
              assertThat(
                      reader
                          .payload("round:resp:1", PayloadVisibility.FULL)
                          .orElseThrow()
                          .content())
                  .containsOnlyOnce("Synthetic scan assistant answer");
            }
            if (scenario.equals("codex_tools")) {
              for (String id : List.of("a", "b")) {
                String marker = id.equals("a") ? "alpha" : "beta";
                assertThat(
                        reader
                            .payload("tool:input:tool-" + id, PayloadVisibility.FULL)
                            .orElseThrow()
                            .content())
                    .contains("/synthetic/" + marker + ".txt");
                assertThat(
                        reader
                            .payload("tool:result:tool-" + id, PayloadVisibility.FULL)
                            .orElseThrow()
                            .content())
                    .isEqualTo("synthetic " + marker + " result");
              }
            }
          }
          if (scenario.equals("codex_dual")) {
            assertThat(compact.calls()).hasSize(1);
          }
          if (scenario.equals("codex_tools")) {
            assertThat(((Number) compact.session().get("declaredTools")).intValue()).isEqualTo(2);
            assertThat(compact.toolExecutions())
                .extracting(tool -> tool.toolCallId())
                .containsExactlyInAnyOrder("tool-a", "tool-b");
            assertThat(compact.toolExecutions())
                .allSatisfy(
                    tool -> {
                      assertThat(tool.name()).isEqualTo("Read");
                      assertThat(compact.calls())
                          .anySatisfy(
                              call -> {
                                assertThat(call.callId()).isEqualTo(tool.declaredByCallId());
                                assertThat(call.response().toolCallIds())
                                    .contains(tool.toolCallId());
                              });
                    });
          }
          if (pending) {
            assertThat(compact.calls()).isEmpty();
            assertThat(compact.toolExecutions()).isEmpty();
            assertThat(scanReader.observedInputPreview())
                .isEqualTo(importReader.observedInputPreview());
          }
          assertThat(rows.next()).isFalse();
        }
        var web =
            new WebCompositionRoot(
                ContractTestComposition.queryRoot(index, new SchemaVersion(1)),
                WebConfig.defaults(),
                new ImportedSessionUseCase(imports));
        JavalinTest.test(
            web.app(),
            (app, client) -> {
              for (String base :
                  List.of(
                      "/api/sessions/" + agent + "/" + SESSION,
                      "/api/imports/" + imported.metadata().importId())) {
                var response = client.get(base + "/rounds");
                assertThat(response.code()).isEqualTo(200);
                var round = JSON.readTree(response.body().string()).at("/rounds/0");
                if (pending) {
                  assertThat(round.path("callCount").asInt()).isZero();
                  assertThat(round.at("/parity/observedInputAvailable").asBoolean()).isTrue();
                  assertThat(round.at("/parity/summary").asText())
                      .contains("Synthetic scan content question");
                }
                if (pending || scenario.equals("qoder_wrapped") || scenario.equals("codex_dual")) {
                  assertThat(round.at("/tokens/provenance/freshInput").asText())
                      .isEqualTo("unknown");
                }
                var payload = client.get(base + "/payload/round:req:1");
                assertThat(payload.code()).isEqualTo(200);
                assertThat(JSON.readTree(payload.body().string()).path("content").asText())
                    .contains("Synthetic scan content question");
                if (scenario.equals("codex_tools")) {
                  assertThat(round.path("toolCallCount").asInt()).isEqualTo(2);
                  assertThat(round.at("/tokens/provenance/freshInput").asText())
                      .as("%s: %s", base, round)
                      .isEqualTo("provider_reported");
                  for (String id : List.of("a", "b")) {
                    var result = client.get(base + "/payload/tool:result:tool-" + id);
                    assertThat(result.code()).isEqualTo(200);
                    assertThat(JSON.readTree(result.body().string()).path("content").asText())
                        .isEqualTo("synthetic " + (id.equals("a") ? "alpha" : "beta") + " result");
                  }
                }
              }
            });
      }
    }
  }
}
