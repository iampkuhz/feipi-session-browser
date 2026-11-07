package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.index.api.write.ScanFailure;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import com.feipi.session.browser.web.WebTestComposition;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ScanStatusApiTest {
  @TempDir Path directory;

  @Test
  void failedStatusIsUncachedIndependentOfPublishedGenerationAndDoesNotLeakLocalIdentity()
      throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("api-status.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url)) {
      var writer = new SqliteIndexWriter(connection);
      writer.ensureSchema();
      var root = WebTestComposition.queryRoot(index, IndexSchema.CURRENT_VERSION);
      var web = new WebCompositionRoot(root, WebConfig.defaults());
      JavalinTest.test(
          web.app(),
          (app, client) -> {
            var unknown = client.get("/api/scan-status");
            assertThat(new ObjectMapper().readTree(unknown.body().string()).path("status").asText())
                .isEqualTo("unknown");
            long initial = writer.startScan(0, "full");
            writer.completeScan(initial, 1, Map.of());
            long failed = writer.startScan(2, "incremental");
            writer.failScan(
                failed,
                3,
                Map.of("codex", 2),
                1,
                List.of(
                    new ScanFailure("codex", "fixture-private-key", "PARSE", "BUFFER_OVERFLOW", 42),
                    new ScanFailure("codex", "fixture-private-key", "PARSE", "BAD_JSON", 43)));
            var response =
                client.get(
                    "/api/scan-status",
                    request -> request.header("X-Session-Index-Generation", "stale-generation"));
            assertThat(response.code()).isEqualTo(200);
            assertThat(response.headers().get("Cache-Control")).containsExactly("no-store");
            String text = response.body().string();
            var body = new ObjectMapper().readTree(text);
            assertThat(body.path("status").asText()).isEqualTo("failure");
            assertThat(body.path("processedCount").asInt()).isEqualTo(2);
            assertThat(body.path("errorCount").asInt()).isEqualTo(1);
            assertThat(body.path("reasons").size()).isEqualTo(2);
            assertThat(body.path("publishedProcessedCount").asInt()).isZero();
            assertThat(body.path("publishedDataAvailable").asBoolean()).isTrue();
            assertThat(text)
                .contains(
                    "BUFFER_OVERFLOW", "Previous successfully published data", "scan --incremental")
                .doesNotContain("fixture-private-key", "sessionKey", "preview", "locator");
          });
    }
  }
}
