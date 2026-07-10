package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** API-first state/error boundaries 的契约测试。 */
@DisplayName("State page and API error contracts")
class StatePagesContractTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("state-pages.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
  }

  @AfterEach
  void tearDown() {
    if (indexConnection != null) {
      indexConnection.close();
    }
  }

  @Test
  @DisplayName("HTML 404 使用 PageStateModel role/aria/actions")
  void html404UsesStateModelAccessibilityContract() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/__missing__");
          assertThat(response.code()).isEqualTo(404);
          String body = response.body().string();
          assertThat(body).contains("Page Not Found");
          assertThat(body).contains("role=\"region\"");
          assertThat(body).contains("aria-live=\"polite\"");
          assertThat(body).contains("href=\"/dashboard\"");
          assertThat(body).contains("href=\"/sessions\"");
          assertThat(body).contains("href=\"/projects\"");
        });
  }

  @Test
  @DisplayName("/api/* 404 返回 JSON envelope，不被 HTML state 覆盖")
  void api404UsesJsonEnvelope() {
    WebCompositionRoot webRoot = createWebRoot();

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/api/unknown");
          assertThat(response.code()).isEqualTo(404);
          assertThat(response.headers().get("Content-Type")).contains("application/json");
          String body = response.body().string();
          assertThat(body).contains("\"error\":\"not_found\"");
          assertThat(body).contains("\"message\"");
          assertThat(body).doesNotContain("state-panel");
        });
  }

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root =
        com.feipi.session.browser.web.WebTestComposition.queryRoot(
            indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }
}
