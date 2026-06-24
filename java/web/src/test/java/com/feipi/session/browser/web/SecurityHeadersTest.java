package com.feipi.session.browser.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import io.javalin.testtools.JavalinTest;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link SecurityHeaders} 集成测试。
 *
 * <p>验证所有 HTTP 响应均携带安全头：CSP、X-Frame-Options、X-Content-Type-Options、Cache-Control。
 */
@DisplayName("安全响应头集成测试")
class SecurityHeadersTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("security-headers-test.db");
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
  @DisplayName("健康检查响应包含全部安全头")
  void healthResponseIncludesSecurityHeaders() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/healthz");
          assertThat(firstHeader(response, "Content-Security-Policy"))
              .contains("default-src 'self'");
          assertThat(firstHeader(response, "X-Frame-Options")).isEqualTo("DENY");
          assertThat(firstHeader(response, "X-Content-Type-Options")).isEqualTo("nosniff");
          assertThat(firstHeader(response, "Cache-Control")).contains("no-store");
          assertThat(firstHeader(response, "X-XSS-Protection")).isEqualTo("0");
          assertThat(firstHeader(response, "Referrer-Policy"))
              .isEqualTo("strict-origin-when-cross-origin");
        });
  }

  @Test
  @DisplayName("404 响应也包含安全头")
  void notFoundResponseIncludesSecurityHeaders() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/nonexistent-page");
          assertThat(firstHeader(response, "Content-Security-Policy"))
              .contains("default-src 'self'");
          assertThat(firstHeader(response, "X-Frame-Options")).isEqualTo("DENY");
        });
  }

  @Test
  @DisplayName("CSP 禁止 frame-ancestors 嵌入")
  void cspDeniesFrameAncestors() {
    assertThat(SecurityHeaders.CSP_VALUE).contains("frame-ancestors 'none'");
  }

  /** 从测试响应中提取指定 header 的第一个值。 */
  private static String firstHeader(io.javalin.testtools.Response response, String name) {
    List<String> values = response.headers().get(name);
    return (values != null && !values.isEmpty()) ? values.get(0) : null;
  }
}
