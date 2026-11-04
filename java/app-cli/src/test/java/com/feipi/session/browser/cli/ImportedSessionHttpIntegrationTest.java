package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 真实 parser → HTTP → SQLite 隔离的端到端合成契约。 */
class ImportedSessionHttpIntegrationTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String SYNTHETIC_SECRET = "SYNTHETIC_ONLY";
  private static final List<String> PERSONAL_APIS =
      List.of(
          "/api/dashboard/summary",
          "/api/dashboard/trends/sessions?grain=week",
          "/api/dashboard/trends/tokens?grain=week",
          "/api/dashboard/trends/prompts?grain=week",
          "/api/dashboard/trends/cache-health?grain=week",
          "/api/dashboard/agents/contribution",
          "/api/sessions/summary",
          "/api/sessions/rows",
          "/api/projects/summary",
          "/api/projects/rows");

  @TempDir Path tempDir;

  @Test
  void realThreeSourceUploadsRemainSeparateFromPersonalTotalsAndEachOther() throws Exception {
    String jdbcUrl = "jdbc:sqlite:" + tempDir.resolve("personal.db").toAbsolutePath();
    var writer = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writer);
    try (var connection = IndexConnection.create(writer, PragmaConfig.DEFAULTS, jdbcUrl);
        var imports =
            new ImportedSessionUseCase(
                new IsolatedSessionImportService(
                    source -> SourceAdapterRegistry.forSourceId(source.getValue())))) {
      IndexSchema.withDefaults().ensureSchema(connection.writerConnection());
      insertPersonalBaseline(connection);
      var repository = new SqliteSessionQueryRepository(connection);
      var queryRoot =
          new QueryCompositionRoot(
              repository,
              new SqliteAggregateQueryRepository(connection),
              new SqliteSessionDetailRepository(repository),
              NormalizedArtifactLoader::load,
              IndexSchema.CURRENT_VERSION.version(),
              QueryCache.withDefaultSize());
      var web = new WebCompositionRoot(queryRoot, WebConfig.defaults(), imports);

      JavalinTest.test(
          web.app(),
          (app, unused) -> {
            try (var api =
                new TestApi(HttpClient.newHttpClient(), "http://localhost:" + app.port())) {
              var before = snapshot(api, queryRoot);
              JsonNode summary = before.get("/api/dashboard/summary");
              assertThat(summary.path("sessionCount").asLong()).isEqualTo(1);
              assertThat(summary.path("projectCount").asLong()).isEqualTo(1);
              assertTokens(summary.path("tokens"), 50, 20, 10, 21, 101);
              List<String> ids = new ArrayList<>();

              for (NormalizedAgent source : NormalizedAgent.values()) {
                boolean codex = source == NormalizedAgent.CODEX;
                var created = api.upload(transcript(source), source.getValue());
                assertThat(created.statusCode()).isEqualTo(201);
                JsonNode navigation = MAPPER.readTree(created.body());
                String id = navigation.path("import_id").asText();
                assertThat(ids).doesNotContain(id);
                ids.add(id);
                assertThat(navigation.path("filename").asText()).isEqualTo("shared.jsonl");
                assertThat(navigation.path("detail_url").asText()).isEqualTo("/imports/" + id);
                assertThat(imports.find(id).orElseThrow().originalSessionId())
                    .isEqualTo("shared-session");
                String base = "/api/imports/" + id;
                assertThat(api.json(base + "/meta").path("sessionKey").asText())
                    .isEqualTo("import:" + id);
                JsonNode metrics = api.json(base + "/metrics");
                assertTokens(
                    metrics.path("tokens"),
                    codex ? 60 : 12,
                    codex ? 40 : 4,
                    3,
                    codex ? 20 : 5,
                    codex ? 123 : 24);
                assertThat(metrics.path("roundCount").asInt()).isPositive();
                assertThat(metrics.path("toolCalls").asInt()).isEqualTo(1);
                api.json(base + "/diagnostics");
                api.json(base + "/rounds");
                api.json(base + "/round/1");
                api.json(base + "/attribution/1/1/request");
                api.json(base + "/attribution/1/1/response");
                for (String kind : List.of("input", "result")) {
                  JsonNode tool = api.json(base + "/payload/tool:" + kind + ":tool-1");
                  assertThat(tool.toString()).contains("[REDACTED]");
                }
                JsonNode bucket = api.json(base + "/bucket-detail/1/request");
                assertThat(bucket.path("kind").asText()).isEqualTo("unavailable");
                assertThat(bucket.path("unavailableReason").asText())
                    .isEqualTo("bucket_detail_source_not_indexed");
                JsonNode payloads = api.json(base + "/payloads").path("payloads");
                assertThat(payloads.isArray()).isTrue();
                assertThat(payloads.size()).isPositive();
                for (JsonNode payload : payloads) {
                  String href = payload.path("apiUrl").asText();
                  assertThat(href).startsWith(base + "/payload/");
                  api.json(href);
                }
                var page = api.get("/imports/" + id);
                assertThat(page.statusCode()).isEqualTo(200);
                assertThat(page.body()).contains("不计入个人统计", "仅本文件分析", base);
                assertThat(page.body()).doesNotContain(SYNTHETIC_SECRET);
                assertThat(snapshot(api, queryRoot)).isEqualTo(before);
                assertPersonalBaseline(connection);
              }

              var duplicate = api.upload(transcript(NormalizedAgent.CLAUDE_CODE), "claude_code");
              assertThat(duplicate.statusCode()).isEqualTo(201);
              String duplicateId = MAPPER.readTree(duplicate.body()).path("import_id").asText();
              assertThat(ids).doesNotContain(duplicateId);
              assertThat(api.delete(ids.getFirst()).statusCode()).isEqualTo(204);
              assertThat(api.get("/api/imports/" + ids.getFirst() + "/meta").statusCode())
                  .isEqualTo(404);
              assertThat(api.get("/api/imports/" + ids.getFirst() + "/round/1").statusCode())
                  .isEqualTo(404);
              assertTokens(
                  api.json("/api/imports/" + duplicateId + "/metrics").path("tokens"),
                  12,
                  4,
                  3,
                  5,
                  24);
              for (String id : ids.subList(1, ids.size())) {
                assertThat(api.get("/api/imports/" + id + "/meta").statusCode()).isEqualTo(200);
              }
              var invalid = api.upload("{invalid synthetic json", "claude_code");
              assertThat(invalid.statusCode()).isEqualTo(400);
              assertThat(invalid.body())
                  .doesNotContain("invalid synthetic json", tempDir.toString());
              assertThat(snapshot(api, queryRoot)).isEqualTo(before);
              assertPersonalBaseline(connection);
            }
          });
    }
  }

  private static String transcript(NormalizedAgent source) {
    String original =
        source == NormalizedAgent.CODEX
            ? ImportedSessionAnalysisIntegrationTest.codexTranscript()
            : ImportedSessionAnalysisIntegrationTest.messageTranscript();
    return original
        .replace("import question", "import question token=" + SYNTHETIC_SECRET)
        .replace("import answer", "import answer token=" + SYNTHETIC_SECRET)
        .replace("synthetic output", "synthetic output token=" + SYNTHETIC_SECRET)
        .replace("echo synthetic", "echo synthetic token=" + SYNTHETIC_SECRET);
  }

  private static Map<String, JsonNode> snapshot(TestApi api, QueryCompositionRoot root)
      throws Exception {
    root.invalidateCache();
    Map<String, JsonNode> result = new LinkedHashMap<>();
    for (String path : PERSONAL_APIS) {
      result.put(path, api.json(path));
    }
    return result;
  }

  private static void assertTokens(
      JsonNode tokens, long fresh, long read, long write, long output, long total) {
    assertThat(tokens.path("fresh").asLong()).isEqualTo(fresh);
    assertThat(tokens.path("cacheRead").asLong()).isEqualTo(read);
    assertThat(tokens.path("cacheWrite").asLong()).isEqualTo(write);
    assertThat(tokens.path("output").asLong()).isEqualTo(output);
    assertThat(tokens.path("total").asLong()).isEqualTo(total);
  }

  private static void insertPersonalBaseline(IndexConnection connection) throws Exception {
    try (var statement =
        connection
            .writerConnection()
            .prepareStatement(
                """
        INSERT INTO sessions (session_key, agent, session_id, title, project_key, ended_at,
          fresh_input_tokens, cache_read_tokens, cache_write_tokens, output_tokens,
          total_tokens, user_message_count)
        VALUES ('claude_code:shared-session', 'claude_code', 'shared-session',
          'Personal baseline', 'personal-project', ?, 50, 20, 10, 21, 101, 1)
        """)) {
      statement.setString(1, LocalDate.now(ZoneOffset.UTC).minusDays(1) + "T12:00:00Z");
      assertThat(statement.executeUpdate()).isEqualTo(1);
    }
  }

  private static void assertPersonalBaseline(IndexConnection connection) throws Exception {
    try (var statement = connection.writerConnection().createStatement();
        var rows = statement.executeQuery("SELECT * FROM sessions")) {
      assertThat(rows.next()).isTrue();
      assertThat(rows.getString("session_key")).isEqualTo("claude_code:shared-session");
      assertThat(rows.getString("session_id")).isEqualTo("shared-session");
      assertThat(rows.getString("title")).isEqualTo("Personal baseline");
      for (var entry :
          Map.of(
                  "fresh_input_tokens",
                  50L,
                  "cache_read_tokens",
                  20L,
                  "cache_write_tokens",
                  10L,
                  "output_tokens",
                  21L,
                  "total_tokens",
                  101L)
              .entrySet()) {
        assertThat(rows.getLong(entry.getKey())).isEqualTo(entry.getValue());
      }
      assertThat(rows.next()).isFalse();
    }
    try (var statement = connection.writerConnection().createStatement();
        var rows = statement.executeQuery("SELECT COUNT(*) FROM session_artifacts")) {
      assertThat(rows.next()).isTrue();
      assertThat(rows.getLong(1)).isZero();
    }
  }

  private record TestApi(HttpClient client, String origin) implements AutoCloseable {
    HttpResponse<String> get(String path) throws Exception {
      return client.send(
          HttpRequest.newBuilder(URI.create(origin + path)).GET().build(),
          HttpResponse.BodyHandlers.ofString());
    }

    JsonNode json(String path) throws Exception {
      var response = get(path);
      assertThat(response.statusCode()).as(path).isEqualTo(200);
      assertThat(response.body()).as("STANDARD response " + path).doesNotContain(SYNTHETIC_SECRET);
      return MAPPER.readTree(response.body());
    }

    HttpResponse<String> upload(String content, String source) throws Exception {
      String body =
          "--synthetic\r\nContent-Disposition: form-data; name=\"source\"\r\n\r\n"
              + source
              + "\r\n--synthetic\r\nContent-Disposition: form-data; name=\"file\"; "
              + "filename=\"../../shared.jsonl\"\r\nContent-Type: application/x-ndjson\r\n\r\n"
              + content
              + "\r\n--synthetic--\r\n";
      return client.send(
          HttpRequest.newBuilder(URI.create(origin + "/api/imports"))
              .header("Origin", origin)
              .header("Content-Type", "multipart/form-data; boundary=synthetic")
              .POST(HttpRequest.BodyPublishers.ofString(body))
              .build(),
          HttpResponse.BodyHandlers.ofString());
    }

    HttpResponse<String> delete(String id) throws Exception {
      return client.send(
          HttpRequest.newBuilder(URI.create(origin + "/api/imports/" + id))
              .header("Origin", origin)
              .DELETE()
              .build(),
          HttpResponse.BodyHandlers.ofString());
    }

    @Override
    public void close() {
      client.close();
    }
  }
}
