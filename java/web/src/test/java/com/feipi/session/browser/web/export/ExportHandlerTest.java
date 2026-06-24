package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.web.WebCompositionRoot;
import com.feipi.session.browser.web.WebConfig;
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
 * {@link ExportHandler} 集成测试。
 *
 * <p>验证导出端点的 content type、安全头和参数校验。
 */
@DisplayName("导出端点集成测试")
class ExportHandlerTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("export-test.db");
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
  @DisplayName("HTML 导出返回正确 content type 和 disposition")
  void htmlExportContentType() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/html?agent=claude-code&session_id=abc123");
          assertThat(response.code()).isEqualTo(200);
          assertThat(firstHeader(response, "Content-Type")).contains("text/html");
          assertThat(firstHeader(response, "Content-Disposition"))
              .contains("attachment")
              .contains("session-abc123.html");
        });
  }

  @Test
  @DisplayName("MHTML 导出返回 multipart content type")
  void mhtmlExportContentType() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/mhtml?agent=claude-code&session_id=abc123");
          assertThat(response.code()).isEqualTo(200);
          assertThat(firstHeader(response, "Content-Type")).contains("multipart/related");
          assertThat(firstHeader(response, "Content-Disposition"))
              .contains("attachment")
              .contains(".mhtml");
        });
  }

  @Test
  @DisplayName("MHTML 导出内容包含 MIME 信封")
  void mhtmlContainsMimeEnvelope() throws Exception {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/mhtml?agent=claude-code&session_id=abc123");
          String body = response.body().string();
          assertThat(body).contains("MIME-Version: 1.0");
          assertThat(body).contains("Content-Type: multipart/related");
          assertThat(body).contains("boundary=");
        });
  }

  @Test
  @DisplayName("缺少 agent 参数返回 400")
  void missingAgentReturns400() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/html?session_id=abc123");
          assertThat(response.code()).isEqualTo(400);
        });
  }

  @Test
  @DisplayName("缺少 session_id 参数返回 400")
  void missingSessionIdReturns400() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/html?agent=claude-code");
          assertThat(response.code()).isEqualTo(400);
        });
  }

  @Test
  @DisplayName("不支持的格式返回 400")
  void unsupportedFormatReturns400() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/pdf?agent=claude-code&session_id=abc123");
          assertThat(response.code()).isEqualTo(400);
        });
  }

  @Test
  @DisplayName("HTML 导出不包含本地绝对路径")
  void htmlExportNoAbsolutePaths() throws Exception {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/html?agent=claude-code&session_id=test-session");
          String body = response.body().string();
          assertThat(body).doesNotContain("/Users/");
          assertThat(body).doesNotContain("C:\\");
        });
  }

  @Test
  @DisplayName("导出响应包含安全头")
  void exportResponseIncludesSecurityHeaders() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

    JavalinTest.test(
        webRoot.app(),
        (testApp, client) -> {
          var response = client.get("/export/html?agent=claude-code&session_id=abc123");
          assertThat(firstHeader(response, "Content-Security-Policy"))
              .contains("default-src 'self'");
          assertThat(firstHeader(response, "X-Frame-Options")).isEqualTo("DENY");
        });
  }

  /** 从测试响应中提取指定 header 的第一个值。 */
  private static String firstHeader(io.javalin.testtools.Response response, String name) {
    List<String> values = response.headers().get(name);
    return (values != null && !values.isEmpty()) ? values.get(0) : null;
  }
}
