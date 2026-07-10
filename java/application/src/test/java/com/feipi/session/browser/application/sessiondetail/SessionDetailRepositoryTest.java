package com.feipi.session.browser.application.sessiondetail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.api.query.SessionArtifactRecord;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link SqliteSessionDetailRepository} 和 {@link SessionDetailRequest} 测试。
 *
 * <p>覆盖会话详情查询、制品元数据查询和请求类型校验。
 */
@DisplayName("SqliteSessionDetailRepository 测试")
class SessionDetailRepositoryTest {

  @TempDir Path tempDir;

  private IndexConnection indexConnection;
  private SqliteSessionDetailRepository repository;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("test-qa050-detail.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    indexConnection = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(indexConnection.writerConnection());
    insertTestData();
    SqliteSessionQueryRepository sessionQueryRepo =
        new SqliteSessionQueryRepository(indexConnection);
    repository = new SqliteSessionDetailRepository(sessionQueryRepo);
  }

  private void insertTestData() throws Exception {
    String sessionSql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name, cwd,"
            + " started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES"
            + " ('cc:s1', 'claude_code', 's1', '测试会话', 'pk1', '项目一', '/work',"
            + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
            + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
            + " 50000, 25000, 15000, 10000, 100000, 0, 2,"
            + " 1704067200, 1704067200, '/f1')";
    indexConnection.writerConnection().createStatement().execute(sessionSql);

    String artifactSql =
        "INSERT INTO session_artifacts"
            + " (session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at)"
            + " VALUES"
            + " ('cc:s1', 'normalized', '/artifacts/cc_s1.json', '1.0', '/source.jsonl',"
            + " 1704067200, 4096, 1704067200, 1704067200)";
    indexConnection.writerConnection().createStatement().execute(artifactSql);
  }

  @Nested
  @DisplayName("SessionDetailRequest 验证")
  class RequestValidation {

    @Test
    @DisplayName("空 sessionKey 抛出异常")
    void emptySessionKeyThrows() {
      assertThatThrownBy(() -> new SessionDetailRequest("", PayloadVisibility.STANDARD))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("sessionKey");
    }

    @Test
    @DisplayName("null sessionKey 抛出异常")
    void nullSessionKeyThrows() {
      assertThatThrownBy(() -> new SessionDetailRequest(null, PayloadVisibility.STANDARD))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("null visibility 抛出异常")
    void nullVisibilityThrows() {
      assertThatThrownBy(() -> new SessionDetailRequest("cc:s1", null))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("factory 方法创建标准请求")
    void standardFactory() {
      SessionDetailRequest req = SessionDetailRequest.standard("cc:s1");
      assertThat(req.sessionKey()).isEqualTo("cc:s1");
      assertThat(req.visibility()).isEqualTo(PayloadVisibility.STANDARD);
    }

    @Test
    @DisplayName("factory 方法创建完整请求")
    void fullFactory() {
      SessionDetailRequest req = SessionDetailRequest.full("cc:s1");
      assertThat(req.sessionKey()).isEqualTo("cc:s1");
      assertThat(req.visibility()).isEqualTo(PayloadVisibility.FULL);
    }
  }

  @Nested
  @DisplayName("findSessionRow 查询")
  class FindSessionRecord {

    @Test
    @DisplayName("存在的会话返回行数据")
    void existingSession() throws Exception {
      Optional<SessionRecord> result = repository.findSessionRow("cc:s1");
      assertThat(result).isPresent();
      assertThat(result.get().sessionKey()).isEqualTo("cc:s1");
      assertThat(result.get().agent()).isEqualTo("claude_code");
      assertThat(result.get().title()).isEqualTo("测试会话");
    }

    @Test
    @DisplayName("canonical route key 可查到 project-scoped Qoder 会话")
    void canonicalRouteKeyFindsProjectScopedSession() throws Exception {
      insertProjectScopedQoderSession();

      Optional<SessionRecord> result =
          repository.findSessionRow("qoder:f2443c59-c6f5-4dc6-ae2d-4e6f1c7c41ea");

      assertThat(result).isPresent();
      assertThat(result.get().sessionKey())
          .isEqualTo("qoder:/work/project:f2443c59-c6f5-4dc6-ae2d-4e6f1c7c41ea");
      assertThat(result.get().title()).isEqualTo("model");
    }

    @Test
    @DisplayName("不存在的会话返回 empty")
    void missingSession() throws Exception {
      Optional<SessionRecord> result = repository.findSessionRow("cc:notexist");
      assertThat(result).isEmpty();
    }
  }

  @Nested
  @DisplayName("findNormalizedArtifact 查询")
  class FindNormalizedArtifact {

    @Test
    @DisplayName("有归一化制品的会话返回制品行")
    void existingArtifact() throws Exception {
      Optional<SessionArtifactRecord> result = repository.findNormalizedArtifact("cc:s1");
      assertThat(result).isPresent();
      assertThat(result.get().artifactType()).isEqualTo("normalized");
      assertThat(result.get().path()).isEqualTo("/artifacts/cc_s1.json");
    }

    @Test
    @DisplayName("canonical route key 可查到 project-scoped session artifact")
    void canonicalRouteKeyFindsProjectScopedArtifact() throws Exception {
      insertProjectScopedQoderSession();

      Optional<SessionArtifactRecord> result =
          repository.findNormalizedArtifact("qoder:f2443c59-c6f5-4dc6-ae2d-4e6f1c7c41ea");

      assertThat(result).isPresent();
      assertThat(result.get().sessionKey())
          .isEqualTo("qoder:/work/project:f2443c59-c6f5-4dc6-ae2d-4e6f1c7c41ea");
      assertThat(result.get().path()).isEqualTo("/artifacts/qoder_project_scoped.json");
    }

    @Test
    @DisplayName("无归一化制品的会话返回 empty")
    void missingArtifact() throws Exception {
      Optional<SessionArtifactRecord> result = repository.findNormalizedArtifact("cc:notexist");
      assertThat(result).isEmpty();
    }

    @Test
    @DisplayName("兼容 main/Python-era normalized_session_json 制品类型")
    void legacyNormalizedSessionJsonArtifact() throws Exception {
      String sql =
          "INSERT INTO session_artifacts"
              + " (session_key, artifact_type, path, schema_version, source_path,"
              + " source_mtime, size_bytes, created_at, updated_at)"
              + " VALUES"
              + " ('cc:s1', 'normalized_session_json', '/artifacts/legacy_cc_s1.json',"
              + " 'session-detail.normalized.v3', '/source.jsonl',"
              + " 1704067200, 8192, 1704067200, 1704067200)";
      indexConnection.writerConnection().createStatement().execute(sql);
      indexConnection
          .writerConnection()
          .createStatement()
          .execute(
              "DELETE FROM session_artifacts WHERE session_key = 'cc:s1' AND artifact_type = 'normalized'");

      Optional<SessionArtifactRecord> result = repository.findNormalizedArtifact("cc:s1");

      assertThat(result).isPresent();
      assertThat(result.get().artifactType()).isEqualTo("normalized_session_json");
      assertThat(result.get().path()).isEqualTo("/artifacts/legacy_cc_s1.json");
    }
  }

  private void insertProjectScopedQoderSession() throws Exception {
    String sessionKey = "qoder:/work/project:f2443c59-c6f5-4dc6-ae2d-4e6f1c7c41ea";
    String sessionSql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name, cwd,"
            + " started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES"
            + " ('"
            + sessionKey
            + "', 'qoder', 'f2443c59-c6f5-4dc6-ae2d-4e6f1c7c41ea', 'model',"
            + " '/work/project', 'project', '/work/project',"
            + " '2024-01-02T00:00:00Z', '2024-01-02T01:00:00Z', 3600, 3000, 600,"
            + " 'Qwen', 'main', 'cli', 1, 1, 1, 10, 20, 30, 40, 100, 0, 0,"
            + " 1704153600, 1704153600, '/qoder.jsonl')";
    indexConnection.writerConnection().createStatement().execute(sessionSql);

    String artifactSql =
        "INSERT INTO session_artifacts"
            + " (session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at)"
            + " VALUES"
            + " ('"
            + sessionKey
            + "', 'normalized', '/artifacts/qoder_project_scoped.json', '1.0',"
            + " '/qoder.jsonl', 1704153600, 1024, 1704153600, 1704153600)";
    indexConnection.writerConnection().createStatement().execute(artifactSql);
  }

  @Nested
  @DisplayName("findArtifacts 查询")
  class FindArtifacts {

    @Test
    @DisplayName("返回会话的全部制品行")
    void allArtifacts() throws Exception {
      var artifacts = repository.findArtifacts("cc:s1");
      assertThat(artifacts).hasSize(1);
      assertThat(artifacts.get(0).sessionKey()).isEqualTo("cc:s1");
    }

    @Test
    @DisplayName("无制品的会话返回空列表")
    void noArtifacts() throws Exception {
      var artifacts = repository.findArtifacts("cc:notexist");
      assertThat(artifacts).isEmpty();
    }
  }
}
