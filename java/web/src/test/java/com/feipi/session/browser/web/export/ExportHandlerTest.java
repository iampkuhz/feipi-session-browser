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
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link ExportHandler} 集成测试。
 *
 * <p>验证导出端点的 content type、安全头、参数校验、session 导出完整性和安全约束。
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

  @Nested
  @DisplayName("Legacy /export/{format} 路由")
  class LegacyExportRoute {

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
  }

  @Nested
  @DisplayName("Session 详情导出路由 /sessions/{agent}/{sessionId}/export.html")
  class SessionExportRoute {

    @Test
    @DisplayName("不存在的会话返回 404")
    void sessionNotFoundReturns404() {
      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/nonexistent/export.html");
            assertThat(response.code()).isEqualTo(404);
          });
    }

    @Test
    @DisplayName("存在的会话返回 200 和正确 content type")
    void existingSessionReturns200() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            assertThat(response.code()).isEqualTo(200);
            assertThat(firstHeader(response, "Content-Type")).contains("text/html");
            assertThat(firstHeader(response, "Content-Disposition"))
                .contains("attachment")
                .contains("session-test-session-1.html");
          });
    }

    @Test
    @DisplayName("导出 HTML 包含 session 标题和基本信息")
    void exportContainsSessionInfo() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).contains("Test Session");
            assertThat(body).contains("claude_code");
            assertThat(body).contains("test-session-1");
            assertThat(body).contains("claude-3-opus");
            assertThat(body).contains("Session Export");
          });
    }

    @Test
    @DisplayName("导出 HTML 包含 session 指标")
    void exportContainsMetrics() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            // Token 组成条图例
            assertThat(body).contains("Fresh");
            assertThat(body).contains("Cache Read");
            assertThat(body).contains("Cache Write");
            assertThat(body).contains("Output");
          });
    }

    @Test
    @DisplayName("导出 HTML 包含 rounds section")
    void exportContainsRoundsSection() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).contains("Rounds");
            // 模板始终渲染 rounds 部分
            assertThat(body).contains("rounds-table");
          });
    }

    @Test
    @DisplayName("导出 HTML 不包含导航链接")
    void exportContainsNoNavigationLinks() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).doesNotContain("<nav");
            assertThat(body).doesNotContain("href=\"/dashboard\"");
            assertThat(body).doesNotContain("href=\"/sessions\"");
            assertThat(body).doesNotContain("href=\"/projects\"");
            assertThat(body).doesNotContain("sidebar");
          });
    }

    @Test
    @DisplayName("导出 HTML 不包含 JS lazy-load")
    void exportContainsNoLazyLoad() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).doesNotContain("lazy_rounds.js");
            assertThat(body).doesNotContain("data-action=\"toggle-round\"");
            assertThat(body).doesNotContain("<script");
          });
    }

    @Test
    @DisplayName("导出 HTML 不包含本地绝对路径")
    void exportNoAbsolutePaths() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).doesNotContain("/Users/");
            assertThat(body).doesNotContain("C:\\");
          });
    }

    @Test
    @DisplayName("导出响应包含安全头")
    void exportSecurityHeaders() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            assertThat(firstHeader(response, "Content-Security-Policy"))
                .contains("default-src 'self'");
            assertThat(firstHeader(response, "X-Frame-Options")).isEqualTo("DENY");
          });
    }

    @Test
    @DisplayName("导出 HTML 是独立 HTML（不继承 base.html）")
    void exportIsStandaloneHtml() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            // 必须以 DOCTYPE 开头
            assertThat(body).startsWith("<!DOCTYPE html>");
            // 不得引用外部 CSS/JS
            assertThat(body).doesNotContain("href=\"/static/css/");
            assertThat(body).doesNotContain("src=\"/static/js/");
            // 必须包含内联样式
            assertThat(body).contains("<style>");
          });
    }

    @Test
    @DisplayName("导出 HTML 包含 payload 可见性状态")
    void exportContainsVisibilityStatus() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).contains("Payload content is hidden");
          });
    }

    @Test
    @DisplayName("导出 HTML 包含 export timestamp")
    void exportContainsTimestamp() throws Exception {
      insertTestSession();

      QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
      WebCompositionRoot webRoot = new WebCompositionRoot(root, WebConfig.defaults());

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1/export.html");
            String body = response.body().string();
            assertThat(body).contains("Exported:");
            assertThat(body).contains("Export generated at");
          });
    }
  }

  @Nested
  @DisplayName("sanitizeFileName")
  class SanitizeFileName {

    @Test
    @DisplayName("保留字母数字和连字符下划线")
    void keepsAlphanumeric() {
      assertThat(ExportHandler.sanitizeFileName("abc-123_XYZ")).isEqualTo("abc-123_XYZ");
    }

    @Test
    @DisplayName("移除非安全字符")
    void removesUnsafeChars() {
      assertThat(ExportHandler.sanitizeFileName("a/b\\c:d")).isEqualTo("abcd");
    }

    @Test
    @DisplayName("空值回退为 export")
    void emptyFallback() {
      assertThat(ExportHandler.sanitizeFileName("///")).isEqualTo("export");
    }

    @Test
    @DisplayName("截断超过 100 字符")
    void truncateLong() {
      String longName = "a".repeat(150);
      assertThat(ExportHandler.sanitizeFileName(longName)).hasSize(100);
    }
  }

  /** 从测试响应中提取指定 header 的第一个值。 */
  private static String firstHeader(io.javalin.testtools.Response response, String name) {
    List<String> values = response.headers().get(name);
    return (values != null && !values.isEmpty()) ? values.get(0) : null;
  }

  /** 插入测试会话数据。 */
  private void insertTestSession() throws Exception {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name,"
            + " cwd, started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES"
            + " ('claude_code:test-session-1', 'claude_code', 'test-session-1',"
            + " 'Test Session', 'pk1', 'Test Project', '/work',"
            + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
            + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
            + " 50000, 25000, 15000, 10000, 100000, 0, 2,"
            + " 1704067200, 1704067200, '/f1')";
    indexConnection.writerConnection().createStatement().execute(sql);
  }
}
