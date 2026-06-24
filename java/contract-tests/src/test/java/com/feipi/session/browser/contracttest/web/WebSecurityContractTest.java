package com.feipi.session.browser.contracttest.web;

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
 * Web 安全契约门禁。
 *
 * <p>验证 XSS 防护、路径穿越防护、payload 可见性默认策略和 CSP 完整性。 本测试位于 HTTP adapter trust boundary，确认安全策略在入口层统一注入。
 */
@DisplayName("WEB-080: Web 安全契约门禁")
class WebSecurityContractTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("security-contract.db");
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

  private WebCompositionRoot createWebRoot() {
    QueryCompositionRoot root = new QueryCompositionRoot(indexConnection, new SchemaVersion(1));
    return new WebCompositionRoot(root, WebConfig.defaults());
  }

  /** 从测试响应中提取指定 header 的第一个值。 */
  private static String firstHeader(io.javalin.testtools.Response response, String name) {
    List<String> values = response.headers().get(name);
    return (values != null && !values.isEmpty()) ? values.get(0) : null;
  }

  @Nested
  @DisplayName("CSP 完整性")
  class CspIntegrity {

    /** 通过 HTTP 响应获取 CSP 值。 */
    private String cspFromResponse() {
      WebCompositionRoot webRoot = createWebRoot();
      final String[] cspHolder = {null};
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            cspHolder[0] = firstHeader(response, "Content-Security-Policy");
          });
      return cspHolder[0];
    }

    @Test
    @DisplayName("CSP 包含 default-src 'self'")
    void cspHasDefaultSrcSelf() {
      assertThat(cspFromResponse()).contains("default-src 'self'");
    }

    @Test
    @DisplayName("CSP 禁止 frame-ancestors")
    void cspDeniesFrameAncestors() {
      assertThat(cspFromResponse()).contains("frame-ancestors 'none'");
    }

    @Test
    @DisplayName("CSP 限制 base-uri 为同源")
    void cspRestrictsBaseUri() {
      assertThat(cspFromResponse()).contains("base-uri 'self'");
    }

    @Test
    @DisplayName("CSP 限制 form-action 为同源")
    void cspRestrictsFormAction() {
      assertThat(cspFromResponse()).contains("form-action 'self'");
    }

    @Test
    @DisplayName("CSP 不允许通配符域")
    void cspNoWildcardDomains() {
      String csp = cspFromResponse();
      // 不允许 *.example.com 之类的通配符域，unsafe-inline 是允许的（Pebble 模板需要）
      assertThat(csp).doesNotContain("*.http");
      assertThat(csp).doesNotContain("* ");
    }

    @Test
    @DisplayName("CSP 不允许外部 CDN 域")
    void cspNoExternalCdn() {
      String csp = cspFromResponse();
      assertThat(csp).doesNotContain("cdn");
      assertThat(csp).doesNotContain("cloudflare");
      assertThat(csp).doesNotContain("googleapis");
      assertThat(csp).doesNotContain("unpkg");
      assertThat(csp).doesNotContain("jsdelivr");
    }
  }

  @Nested
  @DisplayName("XSS 防护")
  class XssProtection {

    @Test
    @DisplayName("X-XSS-Protection 设为 0，避免 mXSS")
    void xssProtectionHeaderIsZero() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            assertThat(firstHeader(response, "X-XSS-Protection")).isEqualTo("0");
          });
    }

    @Test
    @DisplayName("URL 编码的 XSS payload 不出现在 HTML 中")
    void xssPayloadInUrlNotReflected() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            // 尝试在 session detail 路径注入 XSS payload
            String xssPayload = "%3Cscript%3Ealert(1)%3C%2Fscript%3E";
            var response = client.get("/sessions/claude_code/" + xssPayload);
            String body = response.body().string();
            // Pebble 自动转义确保 <script> 不会被注入
            assertThat(body).doesNotContain("<script>alert(1)</script>");
          });
    }

    @Test
    @DisplayName("搜索参数中的 XSS payload 被转义")
    void xssInSearchParamEscaped() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            // URL 编码 XSS payload 避免 Java URI 解析异常
            var response = client.get("/sessions?q=%3Cscript%3Ealert('xss')%3C%2Fscript%3E");
            String body = response.body().string();
            // Pebble 模板转义确保不输出原始 <script>
            assertThat(body).doesNotContain("<script>alert('xss')</script>");
          });
    }

    @Test
    @DisplayName("查询参数中的引号被安全处理")
    void quotesInQueryParamsHandled() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions?q=test%22%3E%3Cimg%20onerror%3Dalert(1)%3E");
            String body = response.body().string();
            assertThat(body).doesNotContain("<img onerror=alert(1)>");
          });
    }
  }

  @Nested
  @DisplayName("路径穿越防护")
  class PathTraversalProtection {

    @Test
    @DisplayName("路径穿越尝试返回 404 或 400")
    void pathTraversalReturnsError() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/../../../etc/passwd");
            // 应该返回 404 或 400，不应返回文件内容
            assertThat(response.code()).isIn(400, 404);
            String body = response.body().string();
            assertThat(body).doesNotContain("root:");
          });
    }

    @Test
    @DisplayName("静态资源路径穿越尝试返回错误")
    void staticPathTraversalReturnsError() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/static/../../etc/passwd");
            assertThat(response.code()).isIn(400, 404);
            String body = response.body().string();
            assertThat(body).doesNotContain("root:");
          });
    }

    @Test
    @DisplayName("API 路径穿越尝试返回错误")
    void apiPathTraversalReturnsError() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/../../etc/passwd/round/1");
            assertThat(response.code()).isIn(400, 404);
          });
    }
  }

  @Nested
  @DisplayName("Payload 可见性默认策略")
  class PayloadVisibilityDefault {

    @Test
    @DisplayName("默认 payload 隐藏，页面显示 Payload hidden 标识")
    void payloadHiddenByDefault() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1");
            String body = response.body().string();
            // 默认 STANDARD 可见性隐藏敏感内容
            assertThat(body).contains("Payload hidden");
            // 不包含实际 payload 内容（没有 raw message 文本）
            assertThat(body).doesNotContain("raw-payload");
          });
    }

    @Test
    @DisplayName("visibility=full 参数不改变默认安全头")
    void fullVisibilityDoesNotWeakenHeaders() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/sessions/claude_code/test-session-1?visibility=full");
            // 即使 visibility=full，安全头不变
            assertThat(firstHeader(response, "Content-Security-Policy"))
                .contains("default-src 'self'");
            assertThat(firstHeader(response, "X-Frame-Options")).isEqualTo("DENY");
          });
    }
  }

  @Nested
  @DisplayName("安全头覆盖所有路由")
  class SecurityHeadersOnAllRoutes {

    @Test
    @DisplayName("404 响应也携带安全头")
    void notFoundHasSecurityHeaders() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/nonexistent-route-xyz");
            assertThat(firstHeader(response, "Content-Security-Policy")).isNotNull();
            assertThat(firstHeader(response, "X-Frame-Options")).isEqualTo("DENY");
            assertThat(firstHeader(response, "X-Content-Type-Options")).isEqualTo("nosniff");
          });
    }

    @Test
    @DisplayName("400 响应也携带安全头")
    void badRequestHasSecurityHeaders() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/only-two-parts");
            assertThat(firstHeader(response, "Content-Security-Policy")).isNotNull();
            assertThat(firstHeader(response, "X-Content-Type-Options")).isEqualTo("nosniff");
          });
    }

    @Test
    @DisplayName("Referrer-Policy 限制 Referer 泄漏")
    void referrerPolicySet() {
      WebCompositionRoot webRoot = createWebRoot();
      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/dashboard");
            assertThat(firstHeader(response, "Referrer-Policy"))
                .isEqualTo("strict-origin-when-cross-origin");
          });
    }
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
