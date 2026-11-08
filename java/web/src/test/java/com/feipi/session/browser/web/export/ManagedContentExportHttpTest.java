package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.sessiondetail.NormalizedArtifactReader;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.io.IOException;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;
import java.util.stream.IntStream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 合成已发布索引贯通真实导出HTTP，不让legacy空壳测试代替managed完整内容与413。 */
class ManagedContentExportHttpTest {
  @TempDir Path directory;
  private IndexConnection index;

  @BeforeEach
  void openPublishedIndex() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("synthetic-export.sqlite");
    var connection = DriverManager.getConnection(url);
    index = IndexConnection.create(connection, PragmaConfig.DEFAULTS, url);
    IndexSchema.ensureSchema(connection);
    try (var statement = connection.createStatement()) {
      statement.executeUpdate(
          "INSERT INTO sessions(session_key,agent,session_id,title,project_key,project_name,"
              + "cwd,started_at,ended_at,duration_seconds,model_execution_seconds,"
              + "tool_execution_seconds,model,git_branch,source,user_message_count,"
              + "assistant_message_count,tool_call_count,output_tokens,fresh_input_tokens,"
              + "cache_read_tokens,cache_write_tokens,total_tokens,failed_tool_count,"
              + "subagent_instance_count,indexed_at,file_mtime,file_path) VALUES("
              + "'codex:synthetic-export','codex','synthetic-export','Synthetic',"
              + "'synthetic-project','Synthetic','','2024-01-01T00:00:00Z',"
              + "'2024-01-01T01:00:00Z',3600,0,0,'synthetic','','cli',1,600,600,"
              + "0,0,0,0,0,0,0,1,1,'synthetic.jsonl')");
    }
    try (var statement =
        connection.prepareStatement(
            "INSERT INTO session_artifacts(session_key,artifact_type,path,schema_version,"
                + "source_path,source_mtime,size_bytes,created_at,updated_at)"
                + " VALUES('codex:synthetic-export','normalized',?,?,'synthetic.jsonl',1,1,1,1)")) {
      statement.setString(1, directory.resolve("synthetic.units").toString());
      statement.setString(2, NormalizedConstants.SCHEMA_VERSION);
      statement.executeUpdate();
    }
  }

  @AfterEach
  void closeIndex() {
    if (index != null) index.close();
  }

  @Test
  void htmlAndMhtmlReachAll600CatalogCallsAndToolsRatherThanFirstWindow() {
    JavalinTest.test(
        app(ContentExportReplayTest.fixture(600)),
        (server, client) -> {
          for (String route :
              List.of(
                  "/sessions/codex/synthetic-export/export.html?visibility=full",
                  "/export/mhtml?agent=codex&session_id=synthetic-export&visibility=full")) {
            var response = client.get(route);
            assertThat(response.code()).isEqualTo(200);
            String body = response.body().string();
            assertThat(response.headers().get("Content-Disposition"))
                .anySatisfy(value -> assertThat(value).contains("attachment"));
            assertThat(body).doesNotContain("fetch(", "<script src");
            var calls =
                Pattern.compile(" · (call-\\d+) · tokens")
                    .matcher(body)
                    .results()
                    .map(match -> match.group(1))
                    .toList();
            assertThat(calls)
                .containsExactlyElementsOf(
                    IntStream.range(0, 600).mapToObj(n -> "call-" + n).toList());
            var tools =
                Pattern.compile("<summary>Tool (tool-\\d+) ·")
                    .matcher(body)
                    .results()
                    .map(match -> match.group(1))
                    .toList();
            assertThat(tools)
                .containsExactlyElementsOf(
                    IntStream.range(0, 600).mapToObj(n -> "tool-" + n).toList());
            assertThat(body).contains("BODY-599-END", "RESULT-599-END", "INPUT-599-END", "Partial");
          }
        });
  }

  @Test
  void offlineRowLabelsMatchConfirmedAndUnknownRowsBeyondTheLiveWindow() {
    var measured =
        new NormalizedCall(
            "token_usage_record:synthetic-response-a",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("turn"),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(),
            List.of(),
            Map.of("modelCallEvidence", "response_usage"),
            Map.of());
    var unknown =
        ContentExportReplayTest.call(
            1, CallScope.MAIN, List.of(), Map.of(), NormalizedCallUsage.empty());
    var unit =
        ContentExportReplayTest.unit(0, List.of(measured, unknown), List.of(), Map.of(), List.of());
    JavalinTest.test(
        app(new ContentExportReplayTest.CountingContent(List.of(unit), 2, 0, 0, 0)),
        (server, client) -> {
          var response = client.get("/api/sessions/codex/synthetic-export/rounds?limit=1");
          assertThat(response.code()).isEqualTo(200);
          var page = new ObjectMapper().readTree(response.body().string());
          assertThat(page.get("roundCount").asInt()).isEqualTo(2);
          assertThat(page.get("modelCallCount").asInt()).isEqualTo(1);
          assertThat(page.get("recordGroupCount").asInt()).isEqualTo(1);
          assertThat(page.get("rounds").size()).isEqualTo(1);
          assertThat(page.get("nextCursor").asText()).isNotBlank();
          for (String route :
              List.of(
                  "/sessions/codex/synthetic-export/export.html",
                  "/export/mhtml?agent=codex&session_id=synthetic-export")) {
            var export = client.get(route);
            assertThat(export.code()).isEqualTo(200);
            assertThat(export.body().string())
                .contains(
                    "Trace rows: 2 · Call records: 2",
                    "Record and row totals are not model API call counts.",
                    "<summary>R1 · " + measured.callId() + " · tokens",
                    "<summary>G2 · " + unknown.callId() + " · tokens")
                .doesNotContain("<summary>R2 ·", "Rounds: 2", " · Calls: 2");
          }
        });
  }

  @Test
  void actualFiftyMiBLimitReturns413WithoutTruncatedHtmlForBothRoutes() {
    JavalinTest.test(
        app(oversizeContent()),
        (server, client) -> {
          for (String route :
              List.of(
                  "/sessions/codex/synthetic-export/export.html",
                  "/export/mhtml?agent=codex&session_id=synthetic-export")) {
            var response = client.get(route);
            assertThat(response.code()).isEqualTo(413);
            assertThat(response.body().string())
                .contains("export_too_large")
                .doesNotContain("<!DOCTYPE html>", "<details>");
          }
        });
  }

  private Javalin app(NormalizedSessionContent content) {
    var sessions = new SqliteSessionQueryRepository(index);
    var reader =
        new NormalizedArtifactReader() {
          public NormalizedSessionArtifact load(Path path) {
            throw new AssertionError("Managed export must never flatten to a legacy artifact");
          }

          public NormalizedSessionContent open(Path path) throws IOException {
            assertThat(path).isEqualTo(directory.resolve("synthetic.units"));
            return content;
          }
        };
    var root =
        new QueryCompositionRoot(
            sessions,
            new SqliteAggregateQueryRepository(index),
            new SqliteSessionDetailRepository(sessions),
            reader,
            1);
    return new WebCompositionRoot(root, WebConfig.defaults()).app();
  }

  private static NormalizedSessionContent oversizeContent() {
    String text = "synthetic-oversize-" + "x".repeat(1024 * 1024);
    var entry =
        new SourceUnitCatalogEntry(
            "body",
            "synthetic.jsonl",
            "synthetic:body",
            "text",
            "synthetic",
            SourceUnitDirection.RESPONSE,
            0,
            0,
            new ByteRange(0, 1),
            "synthetic-hash",
            Optional.empty(),
            Optional.empty(),
            50,
            Optional.empty(),
            Optional.of(text),
            Map.of(),
            Optional.empty(),
            Optional.empty(),
            List.of());
    var units = new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedContentUnit>();
    units.add(
        ContentExportReplayTest.unit(0, List.of(), List.of(), Map.of("body", entry), List.of()));
    for (int n = 0; n < 60; n++) {
      var call =
          new NormalizedCall(
              "big-" + n,
              n + 1,
              "C" + (n + 1),
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.of("shared-turn"),
              "synthetic",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(
                  new SourceUnitRefRange(
                      Optional.empty(), 0, 0, List.of("body"), Optional.of("assistant"))),
              List.of(),
              Map.of(),
              Map.of());
      units.add(ContentExportReplayTest.unit(n + 1, List.of(call), List.of(), Map.of(), List.of()));
    }
    return new ContentExportReplayTest.CountingContent(units, 60, 0, 1, 0);
  }
}
