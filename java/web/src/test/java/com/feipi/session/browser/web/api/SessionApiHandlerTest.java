package com.feipi.session.browser.web.api;

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
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * JSON API 端点集成测试。
 *
 * <p>验证 payload、round、attribution、bucket-detail 和 subagent attribution 路由的 HTTP 行为： 路径验证、错误响应和
 * typed JSON 响应结构。
 *
 * <p>Acceptance contracts: ROUTE-API-012, UI-INTERACTION-003
 */
@DisplayName("SessionApiHandler 集成测试")
class SessionApiHandlerTest {

  @TempDir Path tempDir;
  private IndexConnection indexConnection;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("api-handler-test.db");
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

  @Nested
  @DisplayName("路径验证")
  class PathValidation {

    @Test
    @DisplayName("不足的路径段返回 400")
    void insufficientPathSegmentsReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("bad_request");
          });
    }

    @Test
    @DisplayName("未知资源类型返回 400")
    void unknownResourceReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/session-1/unknown/extra");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("unknown resource");
          });
    }

    @Test
    @DisplayName("非法 round_index 返回 400")
    void invalidRoundIndexReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/session-1/round/abc");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("round_index");
          });
    }

    @Test
    @DisplayName("非正整数 round_index 返回 400")
    void nonPositiveRoundIndexReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/session-1/round/0");
            assertThat(response.code()).isEqualTo(400);
          });
    }

    @Test
    @DisplayName("非法 attribution kind 返回 400")
    void invalidAttributionKindReturns400() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get("/api/sessions/claude_code/test-session-1/attribution/1/1/invalid");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("invalid kind");
          });
    }
  }

  @Nested
  @DisplayName("Payload API")
  class PayloadApi {

    @Test
    @DisplayName("不存在的会话返回 404")
    void sessionNotFoundReturns404() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/nonexistent/payload/main:req:C1");
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("not_found");
            assertThat(body).contains("session not found");
          });
    }

    @Test
    @DisplayName("无制品的会话查找 payload 返回 404")
    void noArtifactPayloadReturns404() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get("/api/sessions/claude_code/test-session-1/payload/main:req:C1");
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("not_found");
          });
    }

    @Test
    @DisplayName("空 payload_id 返回 400")
    void emptyPayloadIdReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/test-session-1/payload/");
            // 路径段不足，400
            assertThat(response.code()).isIn(400, 404);
          });
    }
  }

  @Nested
  @DisplayName("Round API")
  class RoundApi {

    @Test
    @DisplayName("不存在的会话返回 404")
    void sessionNotFoundReturns404() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/nonexistent/round/1");
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("session not found");
          });
    }

    @Test
    @DisplayName("无制品的会话 round 超出范围返回 404")
    void noArtifactRoundOutOfRangeReturns404() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/test-session-1/round/1");
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("out of range");
          });
    }
  }

  @Nested
  @DisplayName("Attribution API")
  class AttributionApi {

    @Test
    @DisplayName("不存在的会话返回 404")
    void sessionNotFoundReturns404() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get("/api/sessions/claude_code/nonexistent/attribution/1/1/request");
            assertThat(response.code()).isEqualTo(404);
          });
    }

    @Test
    @DisplayName("非法 round_index 返回 400")
    void invalidRoundIndexReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get("/api/sessions/claude_code/test-session-1/attribution/0/1/request");
            assertThat(response.code()).isEqualTo(400);
          });
    }

    @Test
    @DisplayName("非法 call_index 返回 400")
    void invalidCallIndexReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get("/api/sessions/claude_code/test-session-1/attribution/1/0/request");
            assertThat(response.code()).isEqualTo(400);
          });
    }

    @Test
    @DisplayName("非法 kind 返回 400")
    void invalidKindReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get("/api/sessions/claude_code/test-session-1/attribution/1/1/badkind");
            assertThat(response.code()).isEqualTo(400);
          });
    }
  }

  @Nested
  @DisplayName("Subagent Attribution API")
  class SubagentAttributionApi {

    @Test
    @DisplayName("不存在的会话返回 404")
    void sessionNotFoundReturns404() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get(
                    "/api/sessions/claude_code/nonexistent/attribution/subagent/sa-1/1/request");
            assertThat(response.code()).isEqualTo(404);
          });
    }

    @Test
    @DisplayName("非法 call_index 返回 400")
    void invalidCallIndexReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get(
                    "/api/sessions/claude_code/test-session-1/attribution/subagent/sa-1/0/request");
            assertThat(response.code()).isEqualTo(400);
          });
    }
  }

  @Nested
  @DisplayName("Bucket Detail API")
  class BucketDetailApi {

    @Test
    @DisplayName("不存在的会话返回 404")
    void sessionNotFoundReturns404() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get(
                    "/api/sessions/claude_code/nonexistent/bucket-detail/1/current_user_message");
            assertThat(response.code()).isEqualTo(404);
          });
    }

    @Test
    @DisplayName("非法 round_index 返回 400")
    void invalidRoundIndexReturns400() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get(
                    "/api/sessions/claude_code/test-session-1/bucket-detail/abc/current_user_message");
            assertThat(response.code()).isEqualTo(400);
          });
    }

    @Test
    @DisplayName("无制品会话 round 超出范围返回 404")
    void roundOutOfRangeReturns404() throws Exception {
      insertTestSession();
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response =
                client.get(
                    "/api/sessions/claude_code/test-session-1/bucket-detail/1/current_user_message");
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("out of range");
          });
    }
  }

  @Nested
  @DisplayName("URL 编码")
  class UrlEncoding {

    @Test
    @DisplayName("URL 编码的 agent 和 sessionId 正确解码")
    void urlEncodedParamsDecoded() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/test%20session/round/1");
            // 会话不存在，但路径解析成功
            assertThat(response.code()).isEqualTo(404);
            String body = response.body().string();
            assertThat(body).contains("session not found");
          });
    }
  }

  @Nested
  @DisplayName("错误响应结构")
  class ErrorEnvelope {

    @Test
    @DisplayName("错误响应包含 error 和 message 字段")
    void errorResponseContainsFields() {
      WebCompositionRoot webRoot = createWebRoot();

      JavalinTest.test(
          webRoot.app(),
          (testApp, client) -> {
            var response = client.get("/api/sessions/claude_code/nonexistent/round/abc");
            assertThat(response.code()).isEqualTo(400);
            String body = response.body().string();
            assertThat(body).contains("\"error\"");
            assertThat(body).contains("\"message\"");
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
