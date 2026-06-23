package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link ArtifactRowMapper} 测试，覆盖归一化制品到 index row 的映射。 */
@DisplayName("ArtifactRowMapper 测试")
class ArtifactRowMapperTest {

  /** 构建最小有效的归一化制品。 */
  private static NormalizedSessionArtifact buildArtifact(
      Map<String, Object> session,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> toolExecutions) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        session,
        calls,
        toolExecutions,
        List.of(),
        Map.of(),
        Map.of());
  }

  /** 创建单个调用。 */
  private static NormalizedCall createCall(
      int index, CallScope scope, NormalizedCallUsage usage, List<String> toolCallIds) {
    return new NormalizedCall(
        "call-" + index,
        index,
        "C" + index,
        scope,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "claude-3",
        Optional.of("2025-01-01T00:0" + index + ":00Z"),
        usage,
        NormalizedCallRequest.empty(),
        new NormalizedCallResponse(toolCallIds),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  /** 创建单个工具执行。 */
  private static NormalizedToolExecution createToolExecution(
      String toolCallId, long durationMs, Optional<String> status) {
    return new NormalizedToolExecution(
        toolCallId,
        "Bash",
        CallScope.MAIN,
        "call-1",
        Optional.empty(),
        status,
        Optional.empty(),
        durationMs,
        List.of(),
        Optional.empty());
  }

  @Nested
  @DisplayName("session map 字段映射")
  class SessionMapMapping {

    @Test
    @DisplayName("全部 session map 字段正确映射到 SessionRow")
    void allSessionFieldsMapped() {
      Map<String, Object> session = new HashMap<>();
      session.put("session_key", "claude_code:abc-123");
      session.put("session_id", "abc-123");
      session.put("title", "测试会话");
      session.put("project_key", "/home/user/project");
      session.put("project_name", "project");
      session.put("cwd", "/home/user/project");
      session.put("started_at", "2025-01-01T00:00:00Z");
      session.put("ended_at", "2025-01-01T01:00:00Z");
      session.put("model", "claude-3-sonnet");
      session.put("git_branch", "main");
      session.put("source", "cli");
      session.put("duration_seconds", 3600.0);

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 1700000000.0, "/path/to/file");

      assertThat(row.sessionKey()).isEqualTo("claude_code:abc-123");
      assertThat(row.sessionId()).isEqualTo("abc-123");
      assertThat(row.title()).isEqualTo("测试会话");
      assertThat(row.projectKey()).isEqualTo("/home/user/project");
      assertThat(row.projectName()).isEqualTo("project");
      assertThat(row.cwd()).isEqualTo("/home/user/project");
      assertThat(row.startedAt()).isEqualTo("2025-01-01T00:00:00Z");
      assertThat(row.endedAt()).isEqualTo("2025-01-01T01:00:00Z");
      assertThat(row.model()).isEqualTo("claude-3-sonnet");
      assertThat(row.gitBranch()).isEqualTo("main");
      assertThat(row.source()).isEqualTo("cli");
      assertThat(row.durationSeconds()).isEqualTo(3600.0);
      assertThat(row.agent()).isEqualTo("claude_code");
      assertThat(row.fileMtime()).isEqualTo(1700000000.0);
      assertThat(row.filePath()).isEqualTo("/path/to/file");
    }

    @Test
    @DisplayName("缺失可选字段默认转换为空字符串")
    void missingOptionalFieldsDefaultToEmpty() {
      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:abc-123",
              "session_id", "abc-123",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.title()).isEmpty();
      assertThat(row.projectKey()).isEmpty();
      assertThat(row.projectName()).isEmpty();
      assertThat(row.cwd()).isEmpty();
      assertThat(row.startedAt()).isEmpty();
      assertThat(row.model()).isEmpty();
      assertThat(row.gitBranch()).isEmpty();
      assertThat(row.source()).isEmpty();
      assertThat(row.filePath()).isEmpty();
    }

    @Test
    @DisplayName("agent 值从 enum 转换为协议字符串")
    void agentEnumToString() {
      Map<String, Object> session =
          Map.of(
              "session_key", "codex:xyz-789",
              "session_id", "xyz-789",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact =
          new NormalizedSessionArtifact(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CODEX,
              List.of(),
              session,
              List.of(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());

      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);
      assertThat(row.agent()).isEqualTo("codex");
    }

    @Test
    @DisplayName("null artifact 时抛 NullPointerException")
    void nullArtifactRejected() {
      assertThatThrownBy(() -> ArtifactRowMapper.toSessionRow(null, 0, null))
          .isInstanceOf(NullPointerException.class);
    }
  }

  @Nested
  @DisplayName("token 聚合")
  class TokenAggregation {

    @Test
    @DisplayName("多个调用的 token 正确累加")
    void tokenAggregationAcrossCalls() {
      NormalizedCallUsage usage1 = new NormalizedCallUsage(100, 50, 20, 80, 250);
      NormalizedCallUsage usage2 = new NormalizedCallUsage(200, 100, 40, 160, 500);
      NormalizedCall call1 = createCall(1, CallScope.MAIN, usage1, List.of("tc-1", "tc-2"));
      NormalizedCall call2 = createCall(2, CallScope.MAIN, usage2, List.of("tc-3"));

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(call1, call2), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.freshInputTokens()).isEqualTo(300);
      assertThat(row.cacheReadTokens()).isEqualTo(150);
      assertThat(row.cacheWriteTokens()).isEqualTo(60);
      assertThat(row.outputTokens()).isEqualTo(240);
      assertThat(row.totalTokens()).isEqualTo(750);
    }

    @Test
    @DisplayName("零调用时 token 全部为零")
    void zeroTokensWithNoCalls() {
      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.freshInputTokens()).isZero();
      assertThat(row.cacheReadTokens()).isZero();
      assertThat(row.cacheWriteTokens()).isZero();
      assertThat(row.outputTokens()).isZero();
      assertThat(row.totalTokens()).isZero();
    }
  }

  @Nested
  @DisplayName("消息和工具计数")
  class MessageAndToolCounts {

    @Test
    @DisplayName("assistant_message_count 等于全部调用数")
    void assistantCountEqualsTotalCalls() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      NormalizedCall call1 = createCall(1, CallScope.MAIN, usage, List.of());
      NormalizedCall call2 = createCall(2, CallScope.SUBAGENT, usage, List.of());

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(call1, call2), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.assistantMessageCount()).isEqualTo(2);
    }

    @Test
    @DisplayName("user_message_count 只统计 MAIN scope 调用")
    void userCountOnlyMainScope() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      NormalizedCall mainCall = createCall(1, CallScope.MAIN, usage, List.of());
      NormalizedCall subCall = createCall(2, CallScope.SUBAGENT, usage, List.of());

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact =
          buildArtifact(session, List.of(mainCall, subCall), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.userMessageCount()).isEqualTo(1);
    }

    @Test
    @DisplayName("tool_call_count 等于所有调用声明的工具调用边之和")
    void toolCallCountFromResponses() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      NormalizedCall call1 = createCall(1, CallScope.MAIN, usage, List.of("tc-1", "tc-2"));
      NormalizedCall call2 = createCall(2, CallScope.MAIN, usage, List.of("tc-3"));

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(call1, call2), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.toolCallCount()).isEqualTo(3);
    }

    @Test
    @DisplayName("failed_tool_count 统计有 status 的工具执行")
    void failedToolCountFromExecutions() {
      NormalizedToolExecution success = createToolExecution("tc-1", 100, Optional.empty());
      NormalizedToolExecution failed =
          createToolExecution("tc-2", 200, Optional.of("error: timeout"));

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact =
          buildArtifact(session, List.of(), List.of(success, failed));
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.failedToolCount()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("时长聚合")
  class DurationAggregation {

    @Test
    @DisplayName("tool_execution_seconds 从毫秒转换为秒")
    void toolExecutionSecondsFromMilliseconds() {
      NormalizedToolExecution exec1 = createToolExecution("tc-1", 1500, Optional.empty());
      NormalizedToolExecution exec2 = createToolExecution("tc-2", 2500, Optional.empty());

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(), List.of(exec1, exec2));
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.toolExecutionSeconds()).isEqualTo(4.0);
    }

    @Test
    @DisplayName("duration_seconds 从 session map 直接取值")
    void durationFromSessionMap() {
      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z",
              "duration_seconds", 120.5);

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.durationSeconds()).isEqualTo(120.5);
    }
  }

  @Nested
  @DisplayName("model 回退")
  class ModelFallback {

    @Test
    @DisplayName("session map 未提供 model 时从第一个 call 取")
    void modelFallsBackToFirstCall() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      NormalizedCall call =
          new NormalizedCall(
              "call-1",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              "claude-3-opus",
              Optional.of("2025-01-01T00:00:00Z"),
              usage,
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(call), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.model()).isEqualTo("claude-3-opus");
    }

    @Test
    @DisplayName("session map 提供 model 时优先使用")
    void sessionMapModelTakesPrecedence() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      NormalizedCall call = createCall(1, CallScope.MAIN, usage, List.of());

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z",
              "model", "claude-3-sonnet");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(call), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.model()).isEqualTo("claude-3-sonnet");
    }
  }

  @Nested
  @DisplayName("子 agent 实例计数")
  class SubagentCounting {

    @Test
    @DisplayName("subagent_instance_count 统计唯一子 agent 实例数")
    void subagentInstanceCountUnique() {
      NormalizedCallUsage usage = NormalizedCallUsage.empty();
      NormalizedCall subCall1 =
          new NormalizedCall(
              "call-2",
              2,
              "C2",
              CallScope.SUBAGENT,
              Optional.of("parent-1"),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              usage,
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());

      NormalizedCall subCall2 =
          new NormalizedCall(
              "call-3",
              3,
              "C3",
              CallScope.SUBAGENT,
              Optional.of("parent-1"),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              usage,
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());

      NormalizedCall subCall3 =
          new NormalizedCall(
              "call-4",
              4,
              "C4",
              CallScope.SUBAGENT,
              Optional.of("parent-2"),
              Optional.empty(),
              Optional.empty(),
              "claude-3",
              Optional.empty(),
              usage,
              NormalizedCallRequest.empty(),
              NormalizedCallResponse.empty(),
              List.of(),
              List.of(),
              Map.of(),
              Map.of());

      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact =
          buildArtifact(session, List.of(subCall1, subCall2, subCall3), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.subagentInstanceCount()).isEqualTo(2);
    }
  }

  @Nested
  @DisplayName("SessionArtifactRow 映射")
  class ArtifactRowMapping {

    @Test
    @DisplayName("toArtifactRow 正确映射全部字段")
    void artifactRowMapping() {
      SessionArtifactRow row =
          ArtifactRowMapper.toArtifactRow(
              "claude_code:test",
              "/artifacts/test.json",
              "session-detail.normalized.v3",
              "/source/test.jsonl",
              1700000000.0,
              5000,
              1700001000.0);

      assertThat(row.sessionKey()).isEqualTo("claude_code:test");
      assertThat(row.artifactType()).isEqualTo(ArtifactRowMapper.ARTIFACT_TYPE_NORMALIZED);
      assertThat(row.path()).isEqualTo("/artifacts/test.json");
      assertThat(row.schemaVersion()).isEqualTo("session-detail.normalized.v3");
      assertThat(row.sourcePath()).isEqualTo("/source/test.jsonl");
      assertThat(row.sourceMtime()).isEqualTo(1700000000.0);
      assertThat(row.sizeBytes()).isEqualTo(5000);
      assertThat(row.createdAt()).isEqualTo(1700001000.0);
      assertThat(row.updatedAt()).isEqualTo(1700001000.0);
    }
  }

  @Nested
  @DisplayName("indexed_at 时间戳")
  class IndexedAt {

    @Test
    @DisplayName("indexed_at 使用当前时间，为正值")
    void indexedAtUsesCurrentTime() {
      Map<String, Object> session =
          Map.of(
              "session_key", "claude_code:test",
              "session_id", "test",
              "ended_at", "2025-01-01T01:00:00Z");

      NormalizedSessionArtifact artifact = buildArtifact(session, List.of(), List.of());
      SessionRow row = ArtifactRowMapper.toSessionRow(artifact, 0, null);

      assertThat(row.indexedAt()).isGreaterThan(0);
    }
  }
}
