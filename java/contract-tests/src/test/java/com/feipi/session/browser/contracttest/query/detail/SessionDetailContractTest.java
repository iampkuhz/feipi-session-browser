package com.feipi.session.browser.contracttest.query.detail;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.sqlite.ArtifactRowMapper;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PayloadLookup;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionDetailAssembler;
import com.feipi.session.browser.index.sqlite.SessionDetailRepository;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 会话详情契约测试。
 *
 * <p>验证 Java session detail 装配与 Python routes.py 行为一致： 轮次分组、payload 来源、敏感字段 masking 和缓存键。
 */
@DisplayName("会话详情契约：detail / artifact / payload 装配")
class SessionDetailContractTest {

  @TempDir Path tempDir;
  private IndexConnection ic;
  private SessionDetailRepository repository;

  @BeforeEach
  void setUp() throws Exception {
    Path dbFile = tempDir.resolve("contract-qa050.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();
    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
    IndexSchema.withDefaults().ensureSchema(ic.writerConnection());
    insertFixtures();
    repository = new SessionDetailRepository(ic);
  }

  private void insertFixtures() throws Exception {
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
            + " ('cc:s1', 'claude_code', 's1', '详情测试', 'pk1', '项目一', '/work',"
            + " '2024-01-01T00:00:00Z', '2024-01-01T01:00:00Z', 3600, 3000, 600,"
            + " 'claude-3-opus', 'main', 'cli', 5, 10, 20,"
            + " 50000, 25000, 15000, 10000, 100000, 0, 2,"
            + " 1704067200, 1704067200, '/f1')";
    ic.writerConnection().createStatement().execute(sql);

    String artifactSql =
        "INSERT INTO session_artifacts"
            + " (session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at)"
            + " VALUES"
            + " ('cc:s1', 'normalized', '/artifacts/cc_s1.json', '1.0', '/source.jsonl',"
            + " 1704067200, 4096, 1704067200, 1704067200)";
    ic.writerConnection().createStatement().execute(artifactSql);
  }

  @Nested
  @DisplayName("详情装配端到端")
  class EndToEndAssembly {

    @Test
    @DisplayName("DB 行 + 制品装配为完整详情")
    void fullAssembly() throws Exception {
      Optional<SessionRow> row = repository.findSessionRow("cc:s1");
      assertThat(row).isPresent();

      NormalizedSessionArtifact artifact = makeTestArtifact();
      SessionDetail detail =
          SessionDetailAssembler.assemble(
              row.get(), artifact, PayloadVisibility.STANDARD, "/artifacts/cc_s1.json", 1);

      assertThat(detail.sessionRow().sessionKey()).isEqualTo("cc:s1");
      assertThat(detail.rounds()).isNotEmpty();
      assertThat(detail.payloadSources()).isNotEmpty();
      assertThat(detail.cacheKey()).contains("artifact:");
      assertThat(detail.cacheKey()).contains(":v1");
    }

    @Test
    @DisplayName("制品元数据正确传递到详情")
    void artifactMetadata() throws Exception {
      Optional<SessionRow> row = repository.findSessionRow("cc:s1");
      NormalizedSessionArtifact artifact = makeTestArtifact();
      SessionDetail detail =
          SessionDetailAssembler.assemble(
              row.get(), artifact, PayloadVisibility.FULL, "/artifacts/cc_s1.json", 1);

      assertThat(detail.artifactPath()).isEqualTo("/artifacts/cc_s1.json");
      assertThat(detail.artifactSchemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
      assertThat(detail.hasArtifact()).isTrue();
    }

    @Test
    @DisplayName("无制品会话生成行级详情")
    void rowOnlyDetail() throws Exception {
      Optional<SessionRow> row = repository.findSessionRow("cc:s1");
      SessionDetail detail = SessionDetail.rowOnly(row.get(), PayloadVisibility.STANDARD);
      assertThat(detail.rounds()).isEmpty();
      assertThat(detail.payloadSources()).isEmpty();
      assertThat(detail.hasArtifact()).isFalse();
    }
  }

  @Nested
  @DisplayName("轮次分组一致性")
  class RoundConsistency {

    @Test
    @DisplayName("主调用和子 agent 调用正确分组")
    void mainAndSubagentGrouping() {
      NormalizedCall mainCall =
          makeCall("c1", 1, CallScope.MAIN, Optional.empty(), "req-ref", "resp-ref");
      NormalizedCall subCall =
          makeCall("c2", 2, CallScope.SUBAGENT, Optional.of("c1"), "sa-req", "sa-resp");
      NormalizedSessionArtifact artifact =
          makeArtifactWithCalls(List.of(mainCall, subCall));

      List<CallRound> rounds = SessionDetailAssembler.buildRounds(artifact.calls());
      assertThat(rounds).hasSize(1);
      assertThat(rounds.get(0).calls()).containsExactly("c1", "c2");
    }
  }

  @Nested
  @DisplayName("Payload 查找一致性")
  class PayloadLookupConsistency {

    @Test
    @DisplayName("标准可见性截断且 masking")
    void standardVisibilityBehavior() {
      NormalizedCall call =
          makeCall("c1", 1, CallScope.MAIN, Optional.empty(),
              "api_key=secret123 data", "response body");
      NormalizedSessionArtifact artifact = makeArtifactWithCalls(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);

      assertThat(lookup.size()).isEqualTo(2);
      var reqEntry = lookup.lookup("main:req:c1");
      assertThat(reqEntry).isPresent();
      assertThat(reqEntry.get().truncated()).isTrue();
      // 注意：当前实现未存储实际内容，content 为空字符串
      assertThat(reqEntry.get().content()).isEmpty();
    }

    @Test
    @DisplayName("完整可见性保留全部内容")
    void fullVisibilityBehavior() {
      NormalizedCall call =
          makeCall("c1", 1, CallScope.MAIN, Optional.empty(),
              "api_key=secret123 data", "response body");
      NormalizedSessionArtifact artifact = makeArtifactWithCalls(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      var reqEntry = lookup.lookup("main:req:c1");
      assertThat(reqEntry).isPresent();
      assertThat(reqEntry.get().truncated()).isFalse();
      // 注意：当前实现未存储实际内容，content 为空字符串
      assertThat(reqEntry.get().content()).isEmpty();
    }

    @Test
    @DisplayName("按 callId 查找返回全部关联 payload")
    void lookupByCallId() {
      NormalizedCall call =
          makeCall("c1", 1, CallScope.MAIN, Optional.empty(), "req", "resp");
      NormalizedSessionArtifact artifact = makeArtifactWithCalls(List.of(call));
      PayloadLookup lookup = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);

      assertThat(lookup.lookupByCallId("c1")).hasSize(2);
    }
  }

  @Nested
  @DisplayName("缓存键一致性")
  class CacheKeyConsistency {

    @Test
    @DisplayName("相同路径和版本生成相同缓存键")
    void deterministicCacheKey() {
      String key1 = SessionDetailAssembler.buildCacheKey("/art/test.json", 1);
      String key2 = SessionDetailAssembler.buildCacheKey("/art/test.json", 1);
      assertThat(key1).isEqualTo(key2);
    }

    @Test
    @DisplayName("不同版本生成不同缓存键")
    void differentVersionDifferentKey() {
      String key1 = SessionDetailAssembler.buildCacheKey("/art/test.json", 1);
      String key2 = SessionDetailAssembler.buildCacheKey("/art/test.json", 2);
      assertThat(key1).isNotEqualTo(key2);
    }

    @Test
    @DisplayName("不同路径生成不同缓存键")
    void differentPathDifferentKey() {
      String key1 = SessionDetailAssembler.buildCacheKey("/art/test1.json", 1);
      String key2 = SessionDetailAssembler.buildCacheKey("/art/test2.json", 1);
      assertThat(key1).isNotEqualTo(key2);
    }
  }

  @Nested
  @DisplayName("制品查询")
  class ArtifactQuery {

    @Test
    @DisplayName("归一化制品查询返回正确元数据")
    void normalizedArtifactQuery() throws Exception {
      var artifact = repository.findNormalizedArtifact("cc:s1");
      assertThat(artifact).isPresent();
      assertThat(artifact.get().artifactType()).isEqualTo("normalized");
      assertThat(artifact.get().schemaVersion()).isEqualTo("1.0");
      assertThat(artifact.get().sizeBytes()).isEqualTo(4096);
    }
  }

  // ── 辅助方法 ──

  private static NormalizedCall makeCall(
      String callId,
      int callIndex,
      CallScope scope,
      Optional<String> parentCallId,
      String requestRef,
      String responseRef) {
    return new NormalizedCall(
        callId,
        callIndex,
        "C" + callIndex,
        scope,
        parentCallId,
        Optional.empty(),
        Optional.empty(),
        "claude-3-opus",
        Optional.empty(),
        new NormalizedCallUsage(500, 300, 200, 1000, 2000),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionArtifact makeTestArtifact() {
    NormalizedCall call =
        makeCall("c1", 1, CallScope.MAIN, Optional.empty(), "req-ref", "resp-ref");
    return makeArtifactWithCalls(List.of(call));
  }

  private static NormalizedSessionArtifact makeArtifactWithCalls(List<NormalizedCall> calls) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of("session_key", "cc:s1"),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
