package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.application.sessiondetail.PayloadLookup;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.ImportedSessionAnalysis;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.index.api.imports.SessionImportPort;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import com.feipi.session.browser.web.WebTestComposition;
import io.javalin.testtools.JavalinTest;
import java.io.IOException;
import java.io.InputStream;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 独立导入的 HTTP 资源范围及安全边界契约。 */
class ImportedSessionApiTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String ID = "11111111-2222-4333-8444-555555555555";
  private static final String BASE = "/api/imports/" + ID;
  @TempDir Path tempDir;
  private IndexConnection connection;
  private FakeImportPort port;
  private WebCompositionRoot web;

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("synthetic.db");
    var writer = DriverManager.getConnection(url);
    PragmaConfig.DEFAULTS.apply(writer);
    connection = IndexConnection.create(writer, PragmaConfig.DEFAULTS, url);
    IndexSchema.ensureSchema(writer);
    ApiContractFixture.insertThreeSessionFixture(connection);
    ApiContractFixture.insertNormalizedArtifactForAlpha(connection, tempDir);
    Path artifactPath = tempDir.resolve("alpha-001.normalized.json");
    ObjectNode artifactJson = (ObjectNode) MAPPER.readTree(Files.readString(artifactPath));
    ((ObjectNode) artifactJson.at("/calls/0"))
        .set(
            "source_units",
            MAPPER.valueToTree(
                java.util.List.of(
                    java.util.Map.of(
                        "role",
                        "assistant",
                        "type",
                        "text",
                        "text",
                        "Synthetic assistant token=SYNTHETIC_ONLY"))));
    Files.writeString(artifactPath, MAPPER.writeValueAsString(artifactJson));
    QueryCompositionRoot query = WebTestComposition.queryRoot(connection, new SchemaVersion(1));
    var fixture =
        query
            .sessionDetail()
            .getDetailContext("claude_code:s-alpha-001", PayloadVisibility.FULL)
            .orElseThrow();
    port =
        new FakeImportPort(
            new ImportedSessionAnalysis(
                new ImportedSessionMetadata(
                    ID,
                    NormalizedAgent.CLAUDE_CODE,
                    "shared.jsonl",
                    "s-alpha-001",
                    8,
                    Instant.parse("2026-01-01T00:00:00Z")),
                fixture.detail().sessionRow(),
                fixture.artifact()));
    web = new WebCompositionRoot(query, WebConfig.defaults(), new ImportedSessionUseCase(port));
  }

  @AfterEach
  void close() throws Exception {
    web.closeImports();
    connection.close();
  }

  @Test
  void importedIdentityKeepsAllResourcesSeparateAndDeletionInvalidatesCache() throws Exception {
    JavalinTest.test(
        web.app(),
        (app, client) -> {
          String before = client.get("/api/dashboard/summary").body().string();
          for (String suffix :
              new String[] {"meta", "metrics", "diagnostics", "rounds", "payloads"}) {
            var response = client.get(BASE + "/" + suffix);
            assertThat(response.code()).as(suffix).isEqualTo(200);
            JsonNode body = MAPPER.readTree(response.body().string());
            assertThat(body.at("/filters/sessionId").asText()).isEqualTo(ID);
            if (suffix.equals("payloads")) {
              assertThat(body.at("/payloads/0/apiUrl").asText()).startsWith(BASE + "/payload/");
            }
            if (suffix.equals("meta")) {
              assertThat(body.at("/parity/sessionFilePath").asText()).isEmpty();
            }
          }
          assertThat(client.get(BASE + "/round/1").code()).isEqualTo(200);
          assertThat(client.get(BASE + "/payload/main%3Areq%3Aalpha-call-1").code()).isEqualTo(200);
          assertThat(client.get(BASE + "/attribution/1/1/request").code()).isEqualTo(200);
          assertThat(client.get(BASE + "/attribution/subagent/sa-alpha/1/request").code())
              .isEqualTo(200);
          assertThat(client.get(BASE + "/attribution/subagent/alpha-call-1/1/request").code())
              .isEqualTo(200);
          assertThat(client.get(BASE + "/attribution/subagent/no-such-agent/1/request").code())
              .isEqualTo(404);
          String page = client.get("/imports/" + ID).body().string();
          assertThat(page).contains("shared.jsonl", BASE).doesNotContain("模板渲染失败");
          assertThat(client.get("/imports").body().string())
              .contains("data-max-bytes=\"209715200\"", "200 MiB", "不计入个人统计")
              .doesNotContain("模板渲染失败");
          assertThat(client.delete(BASE).code()).isEqualTo(204);
          assertThat(client.get(BASE + "/round/1").code()).isEqualTo(404);
          assertThat(client.get(BASE + "/payload/main%3Areq%3Aalpha-call-1").code()).isEqualTo(404);
          assertThat(client.get(BASE + "/meta").code()).isEqualTo(404);
          var missingPage = client.get("/imports/" + ID);
          assertThat(missingPage.code()).isEqualTo(404);
          assertThat(missingPage.body().string()).doesNotContain("模板渲染失败");
          assertThat(client.delete(BASE).code()).isEqualTo(404);
          assertThat(client.get("/api/sessions/claude_code/s-alpha-001/meta").code())
              .isEqualTo(200);
          assertThat(client.get("/api/dashboard/summary").body().string()).isEqualTo(before);
        });
    web.closeImports();
    assertThat(port.closed).isEqualTo(1);
    assertThat(
            web.queryRoot()
                .sessionDetail()
                .getDetailContext("claude_code:s-alpha-001", PayloadVisibility.STANDARD))
        .isPresent();
  }

  @Test
  void uploadTemplateRendersConfiguredResourceAndLifetimeFields() {
    assertThat(
            web.templates()
                .render(
                    "import-session.html",
                    java.util.Map.of(
                        "import_max_bytes",
                        209715200L,
                        "import_max_display",
                        "200 MiB",
                        "import_lifetime_message",
                        "Synthetic lifetime")))
        .contains("data-max-bytes=\"209715200\"", "200 MiB", "Synthetic lifetime");
  }

  @Test
  void standardRoundAssistantSummaryMasksCredentialsWithoutMutatingFullArtifact() {
    JavalinTest.test(
        web.app(),
        (app, client) -> {
          var response = client.get(BASE + "/round/1");
          assertThat(response.code()).isEqualTo(200);
          String body = response.body().string();
          assertThat(MAPPER.readTree(body).at("/round/callAssistantTexts/alpha-call-1").asText())
              .contains("[REDACTED]")
              .doesNotContain("SYNTHETIC_ONLY");
          assertThat(body).doesNotContain("SYNTHETIC_ONLY");
          assertThat(
                  PayloadLookup.fromArtifact(port.analysis.artifact(), PayloadVisibility.FULL)
                      .lookup("main:resp:alpha-call-1")
                      .orElseThrow()
                      .content())
              .contains("SYNTHETIC_ONLY");
        });
  }

  @Test
  void failedServerStartReleasesImportsExactlyOnceWithoutClosingPersonalQueries() throws Exception {
    try (ServerSocket reserved = new ServerSocket(0)) {
      assertThatThrownBy(() -> web.app().start(reserved.getLocalPort()))
          .isInstanceOf(RuntimeException.class);
    } finally {
      web.app().stop();
    }
    web.closeImports();
    assertThat(port.closed).isEqualTo(1);
    assertThat(
            web.queryRoot()
                .sessionDetail()
                .getDetailContext("claude_code:s-alpha-001", PayloadVisibility.STANDARD))
        .isPresent();
  }

  @Test
  void uploadOverDefaultOneMiBLimitReturnsTypedNavigation() {
    JavalinTest.test(
        web.app(),
        (app, client) -> {
          var response = upload(app.port(), "x".repeat(1100 * 1024), "claude_code", null, "");
          assertThat(response.statusCode()).as(response.body()).isEqualTo(201);
          JsonNode result = MAPPER.readTree(response.body());
          assertThat(result.path("import_id").asText()).isEqualTo(ID);
          assertThat(result.path("source").asText()).isEqualTo("claude_code");
          assertThat(result.path("filename").asText()).isEqualTo("shared.jsonl");
          assertThat(result.path("detail_url").asText()).isEqualTo("/imports/" + ID);
          assertThat(result.toString()).doesNotContain(tempDir.toString());
          assertThat(port.uploadedBytes).isEqualTo(1100 * 1024);
        });
  }

  @Test
  void multipartFileLimitReturnsSafe413BeforeParsing() {
    port.maxBytes = 1024;
    web =
        new WebCompositionRoot(
            web.queryRoot(), WebConfig.defaults(), new ImportedSessionUseCase(port));
    JavalinTest.test(
        web.app(),
        (app, client) -> {
          var response = upload(app.port(), "x".repeat(2048), "codex", null, "");
          assertThat(response.statusCode()).as(response.body()).isEqualTo(413);
          assertThat(MAPPER.readTree(response.body()).path("error").asText())
              .isEqualTo("file_too_large");
          assertThat(port.uploadedBytes).isZero();
        });
  }

  @Test
  void rejectsCrossOriginExtraFieldsUnknownSourcesAndNonMultipartInput() {
    JavalinTest.test(
        web.app(),
        (app, client) -> {
          assertThat(
                  upload(app.port(), "{}", "codex", "https://untrusted.invalid", "").statusCode())
              .isEqualTo(403);
          assertThat(upload(app.port(), "{}", "unknown", null, "").statusCode()).isEqualTo(400);
          assertThat(
                  upload(
                          app.port(),
                          "{}",
                          "codex",
                          null,
                          "--fixture\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\n/synthetic/local.jsonl\r\n")
                      .statusCode())
              .isEqualTo(400);
          assertThat(client.post("/api/imports", "{\"path\":\"/synthetic/local.jsonl\"}").code())
              .isEqualTo(400);
          assertThat(client.delete(BASE, "", request -> request.header("Origin", "null")).code())
              .isEqualTo(403);
          assertThat(port.uploadedBytes).isZero();
          assertThat(port.active).isTrue();
        });
  }

  @Test
  void safeImportErrorsHaveExplicitStatusAndSchema() {
    JavalinTest.test(
        web.app(),
        (app, client) -> {
          for (var entry :
              java.util.Map.of(
                      "file_too_large",
                      413,
                      "record_too_large",
                      413,
                      "too_many_records",
                      413,
                      "analysis_too_large",
                      413,
                      "capacity_exceeded",
                      409,
                      "invalid_jsonl",
                      400,
                      "cleanup_failed",
                      500,
                      "service_closed",
                      503)
                  .entrySet()) {
            port.errorCode = entry.getKey();
            var response = upload(app.port(), "{}", "codex", "http://localhost:" + app.port(), "");
            assertThat(response.statusCode()).as(response.body()).isEqualTo(entry.getValue());
            JsonNode body = MAPPER.readTree(response.body());
            assertThat(body.path("error").asText()).isEqualTo(entry.getKey());
            assertThat(body.path("message").asText()).isEqualTo("安全测试错误");
          }
        });
  }

  private static HttpResponse<String> upload(
      int serverPort, String contents, String source, String origin, String extra)
      throws Exception {
    String body =
        "--fixture\r\nContent-Disposition: form-data; name=\"source\"\r\n\r\n"
            + source
            + "\r\n"
            + extra
            + "--fixture\r\nContent-Disposition: form-data; name=\"file\"; filename=\"shared.jsonl\""
            + "\r\nContent-Type: application/json\r\n\r\n"
            + contents
            + "\r\n--fixture--\r\n";
    var request =
        HttpRequest.newBuilder(URI.create("http://localhost:" + serverPort + "/api/imports"))
            .header("Content-Type", "multipart/form-data; boundary=fixture")
            .POST(HttpRequest.BodyPublishers.ofString(body));
    if (origin != null) {
      request.header("Origin", origin);
    }
    try (HttpClient http = HttpClient.newHttpClient()) {
      return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }
  }

  /** 只提供独立内存投影，模拟与个人原始 session ID 碰撞。 */
  private static final class FakeImportPort implements SessionImportPort {
    private final ImportedSessionAnalysis analysis;
    private boolean active = true;
    private String errorCode;
    private long uploadedBytes;
    private long maxBytes = ImportLimits.defaults().maxFileBytes();
    private int closed;

    private FakeImportPort(ImportedSessionAnalysis analysis) {
      this.analysis = analysis;
    }

    @Override
    public ImportedSessionAnalysis create(
        InputStream input, String filename, NormalizedAgent source) throws IOException {
      if (errorCode != null) {
        throw new SessionImportException(errorCode, "安全测试错误");
      }
      uploadedBytes = input.readAllBytes().length;
      active = true;
      return analysis;
    }

    @Override
    public Optional<ImportedSessionAnalysis> find(String id) {
      return active && ID.equals(id) ? Optional.of(analysis) : Optional.empty();
    }

    @Override
    public boolean delete(String id) {
      boolean existed = find(id).isPresent();
      if (existed) {
        active = false;
      }
      return existed;
    }

    @Override
    public ImportLimits limits() {
      return new ImportLimits(maxBytes, 10_000, 1_000_000, 8, 512L * 1024 * 1024);
    }

    @Override
    public void close() {
      active = false;
      closed++;
    }
  }
}
